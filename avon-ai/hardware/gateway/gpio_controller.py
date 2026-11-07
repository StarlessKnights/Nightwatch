#!/usr/bin/env python3
"""
AVON AI - Physical GPIO Control Deck (Raspberry Pi 5 & 3)
Connects physical switches, pushbuttons, and LEDs to the AVON AI simulation REST API.

Supports:
- Raspberry Pi 5 (RP1 southbridge via gpiozero/lgpio)
- Raspberry Pi 3 (BCM2837 via gpiozero)
- Cross-platform Keyboard CLI Fallback (Windows/macOS/Linux without GPIO)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Attempt GPIO import (gpiozero handles Pi 5 with lgpio and Pi 3 natively)
try:
    from gpiozero import Button, LED
    HAS_GPIO = True
except (ImportError, Exception):
    HAS_GPIO = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (GPIO) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AvonGPIO")


class AvonPhysicalController:
    """Manages physical hardware controls and state sync with AVON AI REST API."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.active_trip_fault_id: Optional[str] = None
        self.active_degrade_fault_id: Optional[str] = None
        self.running = True

    # ---------------- API Wrappers ----------------
    def trip_pump_p203(self) -> None:
        """Physical E-Stop / Trip switch engaged for P-203."""
        logger.info("[PHYSICAL INPUT] E-STOP / TRIP engaged on P-203!")
        try:
            resp = requests.post(
                f"{self.api_url}/api/faults",
                json={"type": "PUMP_TRIP", "target": "P-203", "params": {}},
                timeout=2.0
            )
            if resp.status_code == 200:
                self.active_trip_fault_id = resp.json().get("id")
                logger.info(f"Fault injected: {self.active_trip_fault_id}")
            else:
                logger.error(f"Trip failed: {resp.text}")
        except Exception as e:
            logger.error(f"Network error on trip: {e}")

    def clear_trip_pump_p203(self) -> None:
        """Physical E-Stop / Trip switch released for P-203."""
        logger.info("[PHYSICAL INPUT] E-STOP / TRIP cleared on P-203.")
        try:
            # Query active faults to find PUMP_TRIP on P-203
            resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                faults = data.get("snapshot", {}).get("state", {}).get("faults", [])
                for f in faults:
                    if f.get("type") == "PUMP_TRIP" and f.get("target") == "P-203" and f.get("active"):
                        requests.delete(f"{self.api_url}/api/faults/{f['id']}", timeout=2.0)
                        logger.info(f"Cleared fault: {f['id']}")
            self.active_trip_fault_id = None
        except Exception as e:
            logger.error(f"Network error on clear trip: {e}")

    def toggle_degrade_p203(self) -> None:
        """Toggle pump degradation (45% capacity)."""
        if self.active_degrade_fault_id:
            logger.info("[PHYSICAL INPUT] Restoring P-203 to full capacity (100%).")
            try:
                requests.delete(f"{self.api_url}/api/faults/{self.active_degrade_fault_id}", timeout=2.0)
                self.active_degrade_fault_id = None
            except Exception as e:
                logger.error(f"Error clearing degrade fault: {e}")
        else:
            logger.info("[PHYSICAL INPUT] Degrade P-203 to 45% capacity.")
            try:
                resp = requests.post(
                    f"{self.api_url}/api/faults",
                    json={"type": "PUMP_DEGRADE", "target": "P-203", "params": {"capacity_factor": 0.45}},
                    timeout=2.0
                )
                if resp.status_code == 200:
                    self.active_degrade_fault_id = resp.json().get("id")
                    logger.info(f"Degrade fault injected: {self.active_degrade_fault_id}")
            except Exception as e:
                logger.error(f"Error injecting degrade fault: {e}")

    def approve_recommendation(self) -> None:
        """Physical Big Green Button: Approve lowest-cost feasible recommendation."""
        logger.info("[PHYSICAL INPUT] APPROVE BUTTON PRESSED. Fetching best option...")
        try:
            rec_resp = requests.get(f"{self.api_url}/api/recommendation", timeout=2.0)
            if rec_resp.status_code != 200:
                logger.error(f"Could not fetch recommendation: {rec_resp.text}")
                return

            rec = rec_resp.json()
            best_opt = rec.get("best_option_id")
            headline = rec.get("headline", "")

            if not best_opt or best_opt == "DO_NOTHING":
                logger.info(f"No active action to approve. Headline: {headline}")
                return

            # Submit approval
            logger.info(f"Approving recommendation: {best_opt} ({headline})")
            app_resp = requests.post(f"{self.api_url}/api/recommendation/{best_opt}/approve", timeout=2.0)
            if app_resp.status_code == 200:
                logger.info(f"SUCCESS: Operator approved {best_opt} via physical console!")
            else:
                logger.warning(f"Approval failed: {app_resp.text}")

        except Exception as e:
            logger.error(f"Error executing physical approval: {e}")

    def acknowledge_alarms_or_reset(self) -> None:
        """Physical Ack/Reset button: Acknowledges active alarms, or resets if none."""
        logger.info("[PHYSICAL INPUT] ACK / RESET BUTTON PRESSED.")
        try:
            net_resp = requests.get(f"{self.api_url}/api/network", timeout=2.0)
            if net_resp.status_code == 200:
                alarms = net_resp.json().get("snapshot", {}).get("state", {}).get("alarms", [])
                unack = [a for a in alarms if a.get("state") == "ACTIVE_UNACK"]
                if unack:
                    for a in unack:
                        requests.post(f"{self.api_url}/api/alarms/{a['id']}/ack", timeout=2.0)
                        logger.info(f"Acknowledged alarm: {a['tag']} ({a['condition']})")
                    return

            # If no unack alarms, trigger reset
            requests.post(f"{self.api_url}/api/sim/reset", timeout=2.0)
            logger.info("Simulation reset via physical button.")
        except Exception as e:
            logger.error(f"Error on ack/reset: {e}")

    def poll_led_status(self, led_green: Optional[Any], led_yellow: Optional[Any], led_red: Optional[Any]) -> None:
        """Background thread to update physical status indicator LEDs."""
        while self.running:
            try:
                resp = requests.get(f"{self.api_url}/api/network", timeout=1.5)
                if resp.status_code == 200:
                    snapshot = resp.json().get("snapshot", {})
                    state = snapshot.get("state", {})
                    alarms = state.get("alarms", [])
                    tanks = state.get("tanks", {})
                    t104 = tanks.get("T-104", {})

                    has_alarm = len(alarms) > 0 or t104.get("reported", 0.0) >= 900.0
                    intlk_tripped = t104.get("interlock", {}).get("tripped", False)

                    # Check if recommendation is pending
                    rec_resp = requests.get(f"{self.api_url}/api/recommendation", timeout=1.5)
                    has_advisory = False
                    if rec_resp.status_code == 200:
                        rec = rec_resp.json()
                        best = rec.get("best_option_id")
                        has_advisory = best is not None and best != "DO_NOTHING"

                    # Update LEDs
                    if led_green:
                        if not has_alarm and not intlk_tripped and not has_advisory:
                            led_green.on()
                        else:
                            led_green.off()

                    if led_yellow:
                        if has_advisory:
                            led_yellow.on()
                        else:
                            led_yellow.off()

                    if led_red:
                        if intlk_tripped or has_alarm:
                            led_red.on()
                        else:
                            led_red.off()

            except Exception:
                pass
            time.sleep(0.5)


def run_hardware_gpio(cfg: dict, controller: AvonPhysicalController) -> None:
    """Configures physical GPIO pins on Raspberry Pi 5 or 3 using gpiozero."""
    pins = cfg.get("gpio", {}).get("pins", {})
    p_trip = pins.get("trip_switch_p203", 17)
    p_deg = pins.get("degrade_switch_p203", 27)
    p_app = pins.get("approve_button", 22)
    p_rst = pins.get("reset_button", 23)

    p_led_g = pins.get("led_normal_green", 24)
    p_led_y = pins.get("led_advisory_yellow", 25)
    p_led_r = pins.get("led_alarm_red", 8)

    logger.info("Initializing Raspberry Pi physical GPIO lines...")
    logger.info(f" - E-Stop Switch: GPIO {p_trip}")
    logger.info(f" - Degrade Switch: GPIO {p_deg}")
    logger.info(f" - Approve Button: GPIO {p_app}")
    logger.info(f" - Reset/Ack Button: GPIO {p_rst}")

    btn_trip = Button(p_trip, pull_up=True, bounce_time=0.1)
    btn_deg = Button(p_deg, pull_up=True, bounce_time=0.1)
    btn_app = Button(p_app, pull_up=True, bounce_time=0.1)
    btn_rst = Button(p_rst, pull_up=True, bounce_time=0.1)

    led_green = LED(p_led_g) if p_led_g else None
    led_yellow = LED(p_led_y) if p_led_y else None
    led_red = LED(p_led_r) if p_led_r else None

    # Wire button event callbacks
    btn_trip.when_pressed = controller.trip_pump_p203
    btn_trip.when_released = controller.clear_trip_pump_p203

    btn_deg.when_pressed = controller.toggle_degrade_p203
    btn_app.when_pressed = controller.approve_recommendation
    btn_rst.when_pressed = controller.acknowledge_alarms_or_reset

    # Start LED monitor thread
    led_thread = threading.Thread(
        target=controller.poll_led_status,
        args=(led_green, led_yellow, led_red),
        daemon=True
    )
    led_thread.start()

    logger.info("GPIO console active and listening. Ready for physical operator interaction.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("GPIO console stopped.")


def run_interactive_cli(controller: AvonPhysicalController) -> None:
    """Terminal fallback for dev machines or when GPIO is absent."""
    logger.info("=" * 60)
    logger.info("AVON AI PHYSICAL CONSOLE EMULATOR (Keyboard Mode)")
    logger.info("Commands:")
    logger.info(" [t] Toggle E-Stop / Trip on P-203 (Scene 4)")
    logger.info(" [d] Toggle Pump Degrade to 45% (Scene 2)")
    logger.info(" [a] Physical APPROVE Recommendation Button")
    logger.info(" [r] Acknowledge Alarms or Reset Sim")
    logger.info(" [q] Exit")
    logger.info("=" * 60)

    while True:
        try:
            cmd = input("Console > ").strip().lower()
            if cmd == "t":
                if controller.active_trip_fault_id:
                    controller.clear_trip_pump_p203()
                else:
                    controller.trip_pump_p203()
            elif cmd == "d":
                controller.toggle_degrade_p203()
            elif cmd == "a":
                controller.approve_recommendation()
            elif cmd == "r":
                controller.acknowledge_alarms_or_reset()
            elif cmd == "q":
                break
            else:
                print("Unknown command. Use: t, d, a, r, q")
        except (EOFError, KeyboardInterrupt):
            break


def main():
    parser = argparse.ArgumentParser(description="AVON AI Physical GPIO Controller")
    parser.add_argument("--config", default="hardware/gateway/config.json", help="Path to config.json")
    parser.add_argument("--cli", action="store_true", help="Force keyboard CLI emulation mode")
    args = parser.parse_args()

    # Load configuration
    cfg = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    api_url = cfg.get("backend", {}).get("api_url", "http://127.0.0.1:8000")
    controller = AvonPhysicalController(api_url=api_url)

    if HAS_GPIO and not args.cli:
        run_hardware_gpio(cfg, controller)
    else:
        if not HAS_GPIO and not args.cli:
            logger.info("gpiozero/RPi hardware not detected. Running interactive keyboard emulator.")
        run_interactive_cli(controller)


if __name__ == "__main__":
    main()
