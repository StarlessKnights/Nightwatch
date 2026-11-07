#!/usr/bin/env python3
"""
AVON AI - Computer Operator Control Deck
Runs directly on the host computer alongside the web dashboard.
Provides keyboard shortcuts and commands to inject faults, trip pumps,
and trigger operator approval of AVON AI recommendations.
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
    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.active_trip_id: str | None = None
        self.active_degrade_id: str | None = None
        self.active_trt_id: str | None = None

    def trip_p203(self) -> None:
        """Trip P-203 duty pump."""
        if self.active_trip_id:
            print(f"{YELLOW}Clearing P-203 trip fault...{RESET}")
            try:
                requests.delete(f"{self.api_url}/api/faults/{self.active_trip_id}", timeout=2.0)
                self.active_trip_id = None
                print(f"{GREEN}P-203 restored.{RESET}")
            except Exception as e:
                print(f"{RED}Error clearing trip: {e}{RESET}")
        else:
            print(f"{RED}{BOLD}[FAULT] TRIPPING P-203 DUTY PUMP...{RESET}")
            try:
                resp = requests.post(
                    f"{self.api_url}/api/faults",
                    json={"type": "PUMP_TRIP", "target": "P-203", "params": {}},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    self.active_trip_id = resp.json().get("id")
                    print(f"{GREEN}P-203 tripped! Standby P-204 will auto-start after delay (Layer 2).{RESET}")
                else:
                    print(f"{RED}Trip failed: {resp.text}{RESET}")
            except Exception as e:
                print(f"{RED}Network error: {e}{RESET}")

    def degrade_p203(self) -> None:
        """Degrade P-203 to 45% capacity (Scene 2)."""
        if self.active_degrade_id:
            print(f"{YELLOW}Restoring P-203 to 100% capacity...{RESET}")
            try:
                requests.delete(f"{self.api_url}/api/faults/{self.active_degrade_id}", timeout=2.0)
                self.active_degrade_id = None
                print(f"{GREEN}P-203 capacity restored.{RESET}")
            except Exception as e:
                print(f"{RED}Error clearing degrade: {e}{RESET}")
        else:
            print(f"{YELLOW}{BOLD}[FAULT] DEGRADING P-203 TO 45% (flow ~90 bbl/hr)...{RESET}")
            try:
                resp = requests.post(
                    f"{self.api_url}/api/faults",
                    json={"type": "PUMP_DEGRADE", "target": "P-203", "params": {"capacity_factor": 0.45}},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    self.active_degrade_id = resp.json().get("id")
                    print(f"{GREEN}P-203 degraded! Tank T-104 will begin rising toward HH limit.{RESET}")
                else:
                    print(f"{RED}Degrade failed: {resp.text}{RESET}")
            except Exception as e:
                print(f"{RED}Network error: {e}{RESET}")

    def toggle_treatment_constraint(self) -> None:
        """Constrain Treatment Facility TRT-1 to 50% intake (Scene 5)."""
        if self.active_trt_id:
            print(f"{YELLOW}Clearing TRT-1 constraint...{RESET}")
            try:
                requests.delete(f"{self.api_url}/api/faults/{self.active_trt_id}", timeout=2.0)
                self.active_trt_id = None
                print(f"{GREEN}TRT-1 intake restored to 100%.{RESET}")
            except Exception as e:
                print(f"{RED}Error clearing constraint: {e}{RESET}")
        else:
            print(f"{MAGENTA}{BOLD}[FAULT] CONSTRAINING TRT-1 TO 50% INTAKE...{RESET}")
            try:
                resp = requests.post(
                    f"{self.api_url}/api/faults",
                    json={"type": "TREATMENT_CONSTRAINT", "target": "TRT-1", "params": {"intake_factor": 0.5}},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    self.active_trt_id = resp.json().get("id")
                    print(f"{GREEN}TRT-1 constrained! PL-1 & PL-2 will back up both tanks.{RESET}")
                else:
                    print(f"{RED}Constraint failed: {resp.text}{RESET}")
            except Exception as e:
                print(f"{RED}Network error: {e}{RESET}")

    def approve_recommendation(self) -> None:
        """Operator Approval: Approves AVON AI's lowest-cost feasible action."""
        print(f"{CYAN}{BOLD}[OPERATOR ACTION] Requesting AVON AI recommendation...{RESET}")
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

            print(f" Best Option: {GREEN}{BOLD}{best_id}{RESET} (Estimated Savings: ${savings:,.2f})")
            app_resp = requests.post(f"{self.api_url}/api/recommendation/{best_id}/approve", timeout=2.0)
            if app_resp.status_code == 200:
                print(f"{GREEN}{BOLD}✔ APPROVED: Operator approved {best_id}! Plant recovering...{RESET}")
            else:
                print(f"{RED}Approval rejected: {app_resp.text}{RESET}")

        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")

    def status(self) -> None:
        """Print current plant status."""
        try:
            resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if resp.status_code != 200:
                return
            snap = resp.json().get("snapshot", {})
            st = snap.get("state", {})
            tanks = st.get("tanks", {})
            pumps = st.get("pumps", {})
            pipes = st.get("pipelines", {})
            trt = st.get("treatment", {})
            alarms = st.get("alarms", [])

            print(f"\n{BOLD}=== AVON AI LIVE TELEMETRY (t={st.get('t_min', 0)} min) ==={RESET}")
            print(f" Tanks:     T-104: {tanks.get('T-104', {}).get('volume', 0)} bbl | T-101: {tanks.get('T-101', {}).get('volume', 0)} bbl")
            print(f" Pumps:     P-203 ({pumps.get('P-203', {}).get('run_state')} cf={pumps.get('P-203', {}).get('capacity_factor')}) | P-204 ({pumps.get('P-204', {}).get('run_state')}) | P-201 ({pumps.get('P-201', {}).get('run_state')})")
            print(f" Pipelines: PL-1: {pipes.get('PL-1', {}).get('flow', 0)} bbl/hr | PL-2: {pipes.get('PL-2', {}).get('flow', 0)} bbl/hr")
            print(f" Treatment: TRT-1: {trt.get('TRT-1', {}).get('flow', 0)} bbl/hr (factor={trt.get('TRT-1', {}).get('intake_factor')})")
            print(f" Alarms:    {len(alarms)} active alarms\n")
        except Exception as e:
            print(f"{RED}Status query failed: {e}{RESET}")

    def reset_or_ack(self) -> None:
        """Acknowledge alarms or reset simulation."""
        try:
            requests.post(f"{self.api_url}/api/sim/reset", timeout=2.0)
            self.active_trip_id = None
            self.active_degrade_id = None
            self.active_trt_id = None
            print(f"{GREEN}Simulation reset to t=0.{RESET}")
        except Exception as e:
            print(f"{RED}Reset failed: {e}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="AVON AI Operator Control Deck")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="AVON AI REST API URL")
    args = parser.parse_args()

    deck = AvonControlDeck(api_url=args.api)

    print("=" * 65)
    print(f"{BOLD}{CYAN}AVON AI - COMPUTER OPERATOR CONTROL DECK{RESET}")
    print("=" * 65)
    print(f" [{BOLD}t{RESET}] Toggle E-Stop / Trip on P-203 (Scene 4)")
    print(f" [{BOLD}d{RESET}] Toggle Degradation on P-203 (45% capacity, Scene 2)")
    print(f" [{BOLD}c{RESET}] Toggle Treatment Constraint on TRT-1 (Scene 5)")
    print(f" [{BOLD}a{RESET}] {GREEN}{BOLD}APPROVE AVON AI Recommendation{RESET} (Operator action)")
    print(f" [{BOLD}s{RESET}] Print Live Plant Status")
    print(f" [{BOLD}r{RESET}] Reset Simulation")
    print(f" [{BOLD}q{RESET}] Quit")
    print("=" * 65 + "\n")

    while True:
        try:
            cmd = input(f"{BOLD}AvonControl > {RESET}").strip().lower()
            if cmd in ("t", "trip"):
                deck.trip_p203()
            elif cmd in ("d", "degrade"):
                deck.degrade_p203()
            elif cmd in ("c", "constrain"):
                deck.toggle_treatment_constraint()
            elif cmd in ("a", "approve"):
                deck.approve_recommendation()
            elif cmd in ("s", "status"):
                deck.status()
            elif cmd in ("r", "reset"):
                deck.reset_or_ack()
            elif cmd in ("q", "quit", "exit"):
                break
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
