#!/usr/bin/env python3
"""
AVON AI - Computer Operator Control Deck
Runs directly on the host computer alongside the web dashboard.
Provides keyboard shortcuts matching the web client:
  - Trip: Pump fault error button
  - Wear: Health slider between 0 and 1 (bad < 0.5)
  - Unavailability: Operator manual shut down / lockout button
  - Reset: Per-pump reset button to restore a pump to 100% normal
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
                    print(f"{RED}{BOLD}✔ {pump_id} TRIPPED! Watch Arduino display caution triangle / fault. Standby will auto-start.{RESET}")
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
                json={"health": wear_val, "capacity_factor": wear_val},
                timeout=2.0
            )
            if resp.status_code == 200:
                print(f"{GREEN}✔ Wear updated! Arduino display will reflect state live.{RESET}")
            else:
                print(f"{RED}Wear update failed: {resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def toggle_unavailability(self, pump_id: str = "P-204") -> None:
        """Unavailability button: Operator manual shut down / lockout."""
        print(f"{YELLOW}[OPERATOR LOCKOUT] Toggling availability on {pump_id}...{RESET}")
        try:
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
                    status_text = "LOCKED OUT (UNAVAILABLE)" if not new_avail else "RESTORED (AVAILABLE)"
                    print(f"{GREEN}{BOLD}✔ {pump_id} is now {status_text}. Arduino shows solid 'X' when unavailable.{RESET}")
                else:
                    print(f"{RED}Lockout toggle failed: {resp.text}{RESET}")
            else:
                print(f"{RED}Failed to query network snapshot.{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def reset_single_pump(self, pump_id: str) -> None:
        """Reset button for a specific pump: restores wear to 1.0, available to true, and clears its faults."""
        print(f"{CYAN}[RESET PUMP] Resetting {pump_id} to 100% healthy normal state...{RESET}")
        try:
            # 1. Clear any active faults targeting this pump
            net_resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if net_resp.status_code == 200:
                faults = net_resp.json().get("snapshot", {}).get("state", {}).get("faults", [])
                for f in faults:
                    if f.get("target") == pump_id:
                        requests.delete(f"{self.api_url}/api/faults/{f['id']}", timeout=2.0)
                        print(f" Cleared fault: {f['type']} on {pump_id}")

            # 2. Patch wear to 1.0 and available to true
            resp = requests.patch(
                f"{self.api_url}/api/assets/{pump_id}",
                json={"health": 1.0, "capacity_factor": 1.0, "available": True},
                timeout=2.0
            )
            if resp.status_code == 200:
                print(f"{GREEN}{BOLD}✔ {pump_id} fully reset to Normal (100% health, available).{RESET}")
            else:
                print(f"{RED}Reset patch failed: {resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def approve_recommendation(self) -> None:
        """Operator approval button for AVON AI recommendations."""
        print(f"{CYAN}{BOLD}[OPERATOR APPROVE] Checking recommendations...{RESET}")
        try:
            rec_resp = requests.get(f"{self.api_url}/api/recommendation", timeout=2.0)
            if rec_resp.status_code == 200:
                rec_data = rec_resp.json()
                best_id = rec_data.get("best_option_id")
                if best_id:
                    print(f" Approving recommended option: {best_id}...")
                    app_resp = requests.post(
                        f"{self.api_url}/api/recommendation/{best_id}/approve",
                        timeout=2.0
                    )
                    if app_resp.status_code == 200:
                        print(f"{GREEN}{BOLD}✔ Recommendation APPROVED! Mitigation plan active.{RESET}")
                    else:
                        print(f"{RED}Approval failed: {app_resp.text}{RESET}")
                else:
                    print(f"{YELLOW}No actionable recommendation currently proposed by AVON AI.{RESET}")
            else:
                print(f"{RED}Failed to fetch recommendations: {rec_resp.text}{RESET}")
        except Exception as e:
            print(f"{RED}Network error: {e}{RESET}")

    def print_status(self) -> None:
        try:
            resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if resp.status_code == 200:
                state = resp.json().get("snapshot", {}).get("state", {})
                t_min = state.get("t_min", 0)
                pumps = state.get("pumps", {})
                tanks = state.get("tanks", {})
                print(f"\n{BOLD}=== AVON AI Physical Pump Telemetry (t={t_min}m) ==={RESET}")
                for pid, p in pumps.items():
                    cf = p.get("health", p.get("eff_health", 1.0))
                    cf_str = f"{cf:.2f}"
                    avail = "YES" if p.get("available") else "NO (LOCKOUT)"
                    st = p.get("run_state", "STOPPED")
                    print(f"  {pid:6s} | State: {st:8s} | Flow: {p.get('flow', 0):6.1f} bbl/hr | Health: {cf_str} | Available: {avail}")
                for tid, t in tanks.items():
                    vol = t.get("volume", 0)
                    cap = t.get("capacity", 1000)
                    pct = (vol / cap) * 100 if cap else 0
                    print(f"  {tid:6s} | Volume: {vol:6.1f}/{cap} bbl ({pct:.1f}%) | Inflow: {t.get('inflow', 0):.1f} | Outflow: {t.get('outflow', 0):.1f}")
                print("=" * 55 + "\n")
        except Exception as e:
            print(f"{RED}Failed to read status: {e}{RESET}")

    def reset_sim(self) -> None:
        try:
            requests.post(f"{self.api_url}/api/sim/reset", timeout=2.0)
            self.active_trip_id = None
            print(f"{GREEN}✔ Simulation reset to Scenario 1 baseline.{RESET}")
        except Exception as e:
            print(f"{RED}Reset failed: {e}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="AVON AI Computer Operator Control Deck")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080", help="FastAPI backend URL")
    args = parser.parse_args()

    deck = AvonControlDeck(args.api_url)

    print("\n" + "=" * 65)
    print(f"{BOLD}{GREEN} AVON AI OPERATOR TEST CONTROL DECK (3-PUMP ACTIVE / 5-PUMP READY){RESET}")
    print("=" * 65)
    print(f" [{BOLD}t{RESET}] ⚡ TRIP BUTTON on P-203 (Injects pump error)")
    print(f" [{BOLD}w{RESET}] 🎚️ WEAR SLIDER on P-203 (Set wear between 0 and 1)")
    print(f" [{BOLD}u{RESET}] 🔒 UNAVAILABILITY BUTTON on P-204 (Operator shut down)")
    print(f" [{BOLD}r1{RESET}] 🔄 RESET P-201 to 100% Normal (Device 1)")
    print(f" [{BOLD}r2{RESET}] 🔄 RESET P-203 to 100% Normal (Device 2)")
    print(f" [{BOLD}r3{RESET}] 🔄 RESET P-204 to 100% Normal (Device 3)")
    print(f" [{BOLD}a{RESET}] {GREEN}{BOLD}✔ APPROVE BUTTON{RESET} (Operator approves recommendation)")
    print(f" [{BOLD}s{RESET}] 📊 Live Pump Status")
    print(f" [{BOLD}r{RESET}] 🔄 Reset Complete Simulation")
    print(f" [{BOLD}q{RESET}] Quit")
    print("=" * 65 + "\n")

    while True:
        try:
            cmd = input(f"{CYAN}deck> {RESET}").strip().lower()
            if not cmd:
                continue
            if cmd in ("t", "trip"):
                deck.trip_pump("P-203")
            elif cmd.startswith("w") or cmd.startswith("wear"):
                parts = cmd.split()
                val = 0.40 if len(parts) < 2 else float(parts[1])
                deck.set_wear("P-203", max(0.0, min(1.0, val)))
            elif cmd in ("u", "unavail"):
                deck.toggle_unavailability("P-204")
            elif cmd in ("r1", "reset p201"):
                deck.reset_single_pump("P-201")
            elif cmd in ("r2", "reset p203"):
                deck.reset_single_pump("P-203")
            elif cmd in ("r3", "reset p204"):
                deck.reset_single_pump("P-204")
            elif cmd in ("a", "approve"):
                deck.approve_recommendation()
            elif cmd in ("s", "status"):
                deck.print_status()
            elif cmd in ("r", "reset"):
                deck.reset_sim()
            elif cmd in ("q", "quit", "exit"):
                print("Exiting control deck.")
                break
            else:
                print(f"Unknown command: '{cmd}'. Press 's' for status or 'q' to quit.")
        except KeyboardInterrupt:
            print("\nExiting control deck.")
            break
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")


if __name__ == "__main__":
    main()
