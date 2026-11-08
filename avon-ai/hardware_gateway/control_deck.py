#!/usr/bin/env python3
"""
AVON AI - Computer Operator Control Deck
Runs directly on the host computer alongside the web dashboard.
Provides keyboard shortcuts matching the web client:
  - Trip: Pump fault error button
  - Wear: Health slider between 0 and 1 (bad < 0.5)
  - Unavailability: Operator manual shut down / lockout button
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    MAGENTA = Fore.MAGENTA
    BOLD = Style.BRIGHT
    RESET = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = MAGENTA = BOLD = RESET = ""


class AvonControlDeck:
    def __init__(self, api_url: str = "http://127.0.0.1:8080"):
        self.api_url = api_url.rstrip("/")
        self.active_trip_id: str | None = None

    def trip_pump(self, pump_id: str = "P-203") -> None:
        """Trip button: pump error occurs."""
        if self.active_trip_id:
            print(f"{YELLOW}Clearing trip fault on {pump_id}...{RESET}")
            try:
                requests.delete(f"{self.api_url}/api/faults/{self.active_trip_id}", timeout=2.0)
                self.active_trip_id = None
                print(f"{GREEN}✔ Trip cleared! Pump restored.{RESET}")
            except Exception as e:
                print(f"{RED}Error clearing trip: {e}{RESET}")
        else:
            print(f"{RED}{BOLD}⚡ [TRIP BUTTON] Injecting pump trip error on {pump_id}...{RESET}")
            try:
                resp = requests.post(
                    f"{self.api_url}/api/faults",
                    json={"type": "PUMP_TRIP", "target": pump_id, "params": {}},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    self.active_trip_id = resp.json().get("id")
                    print(f"{RED}{BOLD}✔ {pump_id} TRIPPED! Watch Arduino display flashing 'X'. Standby will auto-start.{RESET}")
                else:
                    print(f"{RED}Trip failed: {resp.text}{RESET}")
            except Exception as e:
                print(f"{RED}Network error: {e}{RESET}")

    def set_wear(self, pump_id: str = "P-203", wear_val: float = 0.45) -> None:
        """Wear slider (0 to 1, bad < 0.5)."""
        is_bad = wear_val < 0.5
        color = RED if is_bad else GREEN
        status_label = "BAD (<0.5) DEGRADED" if is_bad else "HEALTHY"
        print(f"{color}[WEAR SLIDER] Setting {pump_id} wear/capacity to {wear_val:.2f} ({status_label})...{RESET}")
        try:
            resp = requests.patch(
                f"{self.api_url}/api/assets/{pump_id}",
                json={"capacity_factor": wear_val},
                timeout=2.0
            )
            if resp.status_code == 200:
                print(f"{GREEN}✔ Wear updated! Arduino impeller will adapt rotation speed live.{RESET}")
            else:
                print(f"{RED}Wear update failed: {resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def toggle_unavailability(self, pump_id: str = "P-204") -> None:
        """Unavailability button: Operator manual shut down / lockout."""
        print(f"{YELLOW}[OPERATOR LOCKOUT] Toggling availability on {pump_id}...{RESET}")
        try:
            # Query current availability
            net_resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if net_resp.status_code == 200:
                pumps = net_resp.json().get("snapshot", {}).get("state", {}).get("pumps", {})
                curr_avail = pumps.get(pump_id, {}).get("available", True)
                new_avail = not curr_avail
                resp = requests.patch(
                    f"{self.api_url}/api/assets/{pump_id}",
                    json={"available": new_avail},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    st_str = "AVAILABLE" if new_avail else "OPERATOR SHUT DOWN (LOCKED OUT)"
                    print(f"{GREEN}✔ {pump_id} is now {st_str}. Arduino will show lockout slash.{RESET}")
                else:
                    print(f"{RED}Failed: {resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def approve_recommendation(self) -> None:
        """Operator approval button for AVON AI recommendations."""
        print(f"{CYAN}{BOLD}[OPERATOR APPROVE] Checking recommendations...{RESET}")
        try:
            resp = requests.get(f"{self.api_url}/api/recommendation", timeout=2.0)
            if resp.status_code != 200:
                print(f"{RED}Could not fetch recommendation: {resp.text}{RESET}")
                return

            rec = resp.json()
            best_id = rec.get("best_option_id")
            headline = rec.get("headline", "")
            savings = rec.get("savings", 0.0)

            print(f" Headline: {BOLD}{headline}{RESET}")
            if not best_id or best_id == "DO_NOTHING":
                print(f"{YELLOW}No action required. Plant operating within limits.{RESET}")
                return

            print(f" Approving: {GREEN}{BOLD}{best_id}{RESET} (Avoided Loss: ${savings:,.2f})")
            app_resp = requests.post(f"{self.api_url}/api/recommendation/{best_id}/approve", timeout=2.0)
            if app_resp.status_code == 200:
                print(f"{GREEN}{BOLD}✔ APPROVED: Operator approved {best_id}! Watch standby pump spin up.{RESET}")
            else:
                print(f"{RED}Approval rejected: {app_resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")

    def status(self) -> None:
        try:
            resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if resp.status_code != 200:
                return
            snap = resp.json().get("snapshot", {})
            st = snap.get("state", {})
            pumps = st.get("pumps", {})
            tanks = st.get("tanks", {})

            print(f"\n{BOLD}=== LIVE PUMP TELEMETRY (t={st.get('t_min', 0)} min) ==={RESET}")
            for pid in ["P-203", "P-204", "P-201"]:
                p = pumps.get(pid, {})
                cf = p.get("capacity_factor", 1.0)
                wear_badge = f"{RED}WEAR {cf*100:.0f}% (<0.5 BAD){RESET}" if cf < 0.5 else f"{GREEN}WEAR {cf*100:.0f}%{RESET}"
                avail_badge = f"{GREEN}AVAILABLE{RESET}" if p.get("available") else f"{RED}LOCKED OUT{RESET}"
                print(f" {BOLD}{pid}{RESET} ({p.get('role')}): {p.get('run_state')} | Flow: {p.get('flow', 0):.0f} bbl/hr | {wear_badge} | {avail_badge}")
            print(f" Tanks: T-104: {tanks.get('T-104', {}).get('volume', 0):.0f} bbl | T-101: {tanks.get('T-101', {}).get('volume', 0):.0f} bbl\n")
        except Exception as e:
            print(f"{RED}Status query failed: {e}{RESET}")

    def reset_sim(self) -> None:
        try:
            requests.post(f"{self.api_url}/api/sim/reset", timeout=2.0)
            self.active_trip_id = None
            print(f"{GREEN}✔ Simulation reset to t=0.{RESET}")
        except Exception as e:
            print(f"{RED}Reset failed: {e}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="AVON AI Operator Control Deck")
    parser.add_argument("--api", default="http://127.0.0.1:8080", help="AVON AI REST API URL")
    args = parser.parse_args()

    deck = AvonControlDeck(api_url=args.api)

    print("=" * 65)
    print(f"{BOLD}{CYAN}AVON AI - 3-PUMP OPERATOR HARDWARE TEST DECK{RESET}")
    print("=" * 65)
    print(f" [{BOLD}t{RESET}] ⚡ TRIP BUTTON on P-203 (Injects pump error)")
    print(f" [{BOLD}w{RESET}] 🎚️ WEAR SLIDER on P-203 (Set wear between 0 and 1)")
    print(f" [{BOLD}u{RESET}] 🔒 UNAVAILABILITY BUTTON on P-204 (Operator shut down)")
    print(f" [{BOLD}a{RESET}] {GREEN}{BOLD}✔ APPROVE BUTTON{RESET} (Operator approves recommendation)")
    print(f" [{BOLD}s{RESET}] 📊 Live Pump Status")
    print(f" [{BOLD}r{RESET}] 🔄 Reset Simulation")
    print(f" [{BOLD}q{RESET}] Quit")
    print("=" * 65 + "\n")

    while True:
        try:
            cmd = input(f"{BOLD}AvonControl > {RESET}").strip().lower()
            if cmd in ("t", "trip"):
                deck.trip_pump("P-203")
            elif cmd in ("w", "wear"):
                val_str = input("Enter wear value (0.0 to 1.0, bad < 0.5) [default 0.45]: ").strip()
                val = float(val_str) if val_str else 0.45
                deck.set_wear("P-203", max(0.0, min(1.0, val)))
            elif cmd in ("u", "unavail"):
                deck.toggle_unavailability("P-204")
            elif cmd in ("a", "approve"):
                deck.approve_recommendation()
            elif cmd in ("s", "status"):
                deck.status()
            elif cmd in ("r", "reset"):
                deck.reset_sim()
            elif cmd in ("q", "quit", "exit"):
                break
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
