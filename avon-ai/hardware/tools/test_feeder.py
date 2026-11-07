#!/usr/bin/env python3
"""
AVON AI - Arduino Hardware Test Feeder
Standalone tool for Person B to test 12x8 LED Matrix animations
without needing the full backend/frontend running.

Usage:
    python hardware/tools/test_feeder.py --port COM3 --device 2 --interactive
    python hardware/tools/test_feeder.py --scenario degrade
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


def print_ascii_matrix_preview(flow: float, frame: int) -> None:
    """Renders a simple 12x8 terminal preview of the waterflow animation."""
    print("\033[H\033[J", end="") # Clear terminal screen
    print(f"=== 12x8 LED Matrix Preview (PL-1 Waterflow @ {flow:.1f} bbl/hr) ===")
    
    # 8 rows x 12 cols
    lines = []
    lines.append("+------------+") # Top wall
    for r in range(1, 7):
        row_str = "|"
        for c in range(12):
            if flow <= 1.0:
                row_str += "-" if r in (3, 4) and c in (3, 4, 7, 8) else " "
            else:
                # Moving wave pattern
                val = math.sin((c - frame * 0.8) * 0.9)
                if r in (3, 4) and val > 0.0:
                    row_str += ">"
                elif r in (2, 5) and val > 0.5:
                    row_str += "~"
                else:
                    row_str += " "
        row_str += "|"
        lines.append(row_str)
    lines.append("+------------+") # Bottom wall
    
    print("\n".join(lines))
    delay_ms = 500 if flow <= 1 else max(35, min(320, int(320 - (flow / 250.0) * 280)))
    print(f"Frame Delay: {delay_ms} ms | Animation State: {'FROZEN' if flow <= 1 else 'FLOWING'}")


def send_packet(ser, payload: dict, dev_id: int) -> None:
    line = json.dumps(payload, separators=(',', ':')) + "\n"
    if ser:
        try:
            ser.write(line.encode("utf-8"))
            ser.flush()
        except Exception as e:
            print(f"[Error writing serial]: {e}")
    print(f"[TX -> Dev {dev_id}]: {line.strip()}")


def run_interactive(port_name: str | None, baud: int, target_dev: int) -> None:
    ser = None
    if port_name and HAS_SERIAL:
        try:
            ser = serial.Serial(port_name, baud, timeout=0.1)
            print(f"Connected to Arduino on {port_name} @ {baud}")
        except Exception as e:
            print(f"Could not open {port_name}: {e}. Running in preview mode.")

    flow = 200.0
    level = 600.0
    frame = 0
    running = True

    print("\nControls:")
    print("  [+] Increase flow rate (+20 bbl/hr)")
    print("  [-] Decrease flow rate (-20 bbl/hr)")
    print("  [0] Zero flow (Tripped pump)")
    print("  [1] Degraded flow (90 bbl/hr)")
    print("  [2] Normal flow (200 bbl/hr)")
    print("  [3] Max flow (250 bbl/hr)")
    print("  [h] High-High Alarm toggle")
    print("  [q] Quit\n")

    try:
        import msvcrt # Windows
        def get_key():
            if msvcrt.kbhit():
                return msvcrt.getch().decode("utf-8", errors="ignore").lower()
            return None
    except ImportError: # Linux/Mac
        import select
        def get_key():
            dr, _, _ = select.select([sys.stdin], [], [], 0)
            if dr:
                return sys.stdin.read(1).lower()
            return None

    last_tx = 0.0
    alarm_hh = False

    while running:
        key = get_key()
        if key == '+':
            flow = min(250.0, flow + 20.0)
        elif key == '-':
            flow = max(0.0, flow - 20.0)
        elif key == '0':
            flow = 0.0
        elif key == '1':
            flow = 90.0
        elif key == '2':
            flow = 200.0
        elif key == '3':
            flow = 250.0
        elif key == 'h':
            alarm_hh = not alarm_hh
            level = 955.0 if alarm_hh else 600.0
        elif key == 'q':
            break

        now = time.monotonic()
        if now - last_tx >= 0.15: # ~6 Hz update
            last_tx = now
            frame += 1

            if target_dev == 1:
                pkt = {
                    "dev": 1,
                    "lvl": level,
                    "cap": 1000.0,
                    "inflow": 180.0,
                    "outflow": flow,
                    "p203": {"state": 2 if flow == 0 else 1, "cf": round(flow / 200.0, 2), "label": "TRIPPED" if flow == 0 else "RUNNING"},
                    "p204": {"state": 0, "cf": 1.0, "label": "STOPPED"},
                    "alarm": 2 if level >= 950 else (1 if level >= 900 else 0),
                    "interlock": 1 if level >= 950 else 0
                }
            elif target_dev == 2:
                pkt = {
                    "dev": 2,
                    "flow": flow,
                    "cap": 250.0,
                    "restr": 1.0,
                    "dir": 1 if flow > 0 else 0,
                    "alarm": 0
                }
            else:
                pkt = {
                    "dev": 3,
                    "flow": flow,
                    "cap": 400.0,
                    "intake_factor": 1.0,
                    "alarm": 0
                }

            send_packet(ser, pkt, target_dev)
            if not ser:
                print_ascii_matrix_preview(flow, frame)

        time.sleep(0.05)

    if ser:
        ser.close()


def run_scenario(scenario: str, port_name: str | None, baud: int, target_dev: int) -> None:
    ser = None
    if port_name and HAS_SERIAL:
        try:
            ser = serial.Serial(port_name, baud, timeout=0.1)
            print(f"Connected to Arduino on {port_name}")
        except Exception as e:
            print(f"Serial port unavailable: {e}")

    print(f"Running automated test scenario: {scenario.upper()}")
    
    if scenario == "normal":
        pkt = {"dev": target_dev, "flow": 200.0, "cap": 250.0, "restr": 1.0, "dir": 1, "alarm": 0}
        send_packet(ser, pkt, target_dev)
    elif scenario == "degrade":
        print("Emulating Scene 2 (Pump degradation to 90 bbl/hr)...")
        for f in range(200, 80, -10):
            pkt = {"dev": target_dev, "flow": float(f), "cap": 250.0, "restr": 1.0, "dir": 1, "alarm": 0}
            send_packet(ser, pkt, target_dev)
            time.sleep(0.4)
    elif scenario == "trip":
        print("Emulating Scene 4 (Pump trip -> zero flow -> standby restart)...")
        # 1. Running
        pkt = {"dev": target_dev, "flow": 200.0, "cap": 250.0, "restr": 1.0, "dir": 1, "alarm": 0}
        send_packet(ser, pkt, target_dev)
        time.sleep(2)
        # 2. Trip
        print("PUMP TRIPPED! Flow = 0")
        pkt = {"dev": target_dev, "flow": 0.0, "cap": 250.0, "restr": 1.0, "dir": 0, "alarm": 1}
        send_packet(ser, pkt, target_dev)
        time.sleep(3)
        # 3. Standby Auto-start
        print("STANDBY AUTO-STARTED! Flow resumes to 200 bbl/hr")
        pkt = {"dev": target_dev, "flow": 200.0, "cap": 250.0, "restr": 1.0, "dir": 1, "alarm": 0}
        send_packet(ser, pkt, target_dev)

    if ser:
        ser.close()


def main():
    parser = argparse.ArgumentParser(description="AVON AI Hardware Test Feeder")
    parser.add_argument("--port", help="Serial port (e.g. COM3 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    parser.add_argument("--device", type=int, default=2, choices=[1, 2, 3], help="Target Device ID")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive control slider")
    parser.add_argument("--scenario", choices=["normal", "degrade", "trip"], help="Run automated scenario")
    args = parser.parse_args()

    if args.scenario:
        run_scenario(args.scenario, args.port, args.baud, args.device)
    else:
        run_interactive(args.port, args.baud, args.device)


if __name__ == "__main__":
    main()
