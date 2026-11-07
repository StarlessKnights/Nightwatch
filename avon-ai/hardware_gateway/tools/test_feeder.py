#!/usr/bin/env python3
"""
AVON AI - Physical Pump Test Feeder
Standalone tool to test the 12x8 LED Matrix pump animations on any of the 5 Arduinos.

Usage:
    py hardware_gateway/tools/test_feeder.py --device 1 --interactive
    py hardware_gateway/tools/test_feeder.py --device 1 --scenario trip
"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

PUMP_NAMES = {
    1: "P-203 (Duty T-104)",
    2: "P-204 (Standby T-104)",
    3: "P-201 (Duty T-101)",
    4: "P-SRC1 (Wellhead Inflow 1)",
    5: "P-SRC2 (Wellhead Inflow 2)"
}


def print_pump_ascii_preview(pump_name: str, state: int, flow: float, frame: int) -> None:
    print("\033[H\033[J", end="")
    state_labels = ["STOPPED", "RUNNING", "STARTING", "DEGRADED", "TRIPPED", "UNAVAILABLE"]
    st_name = state_labels[state] if state < len(state_labels) else "UNKNOWN"

    print(f"=== Pump Matrix Preview ({pump_name}) ===")
    print(f"State: {st_name} | Flow: {flow:.1f} bbl/hr\n")

    rotStep = frame % 4
    lines = [
        "   +------+   ",
        "===|  {}  |===".format("/\\" if rotStep % 2 == 0 else "||"),
        " > | ({}) | > ".format("X" if state == 4 else ("O" if rotStep == 0 else ("/" if rotStep == 1 else ("|" if rotStep == 2 else "\\")))),
        " > | ({}) | > ".format("X" if state == 4 else ("O" if rotStep == 0 else ("/" if rotStep == 1 else ("|" if rotStep == 2 else "\\")))),
        "===|  {}  |===".format("\\/" if rotStep % 2 == 0 else "||"),
        "   +------+   "
    ]
    print("\n".join(lines))


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
    state = 1 # Running
    frame = 0
    pname = PUMP_NAMES.get(target_dev, f"Pump {target_dev}")

    print(f"\nControls for {pname}:")
    print("  [1] Set state to RUNNING (200 bbl/hr, full speed spin)")
    print("  [2] Set state to STARTING (pulsing)")
    print("  [3] Set state to DEGRADED (90 bbl/hr, labored spin)")
    print("  [4] Set state to TRIPPED (0 bbl/hr, flashing 'X')")
    print("  [0] Set state to STOPPED (0 bbl/hr, idle)")
    print("  [+] Increase flow rate (+20 bbl/hr)")
    print("  [-] Decrease flow rate (-20 bbl/hr)")
    print("  [q] Quit\n")

    try:
        import msvcrt
        def get_key():
            if msvcrt.kbhit():
                return msvcrt.getch().decode("utf-8", errors="ignore").lower()
            return None
    except ImportError:
        import select
        def get_key():
            dr, _, _ = select.select([sys.stdin], [], [], 0)
            if dr:
                return sys.stdin.read(1).lower()
            return None

    last_tx = 0.0

    while True:
        key = get_key()
        if key == '1':
            state, flow = 1, 200.0
        elif key == '2':
            state, flow = 2, 0.0
        elif key == '3':
            state, flow = 3, 90.0
        elif key == '4':
            state, flow = 4, 0.0
        elif key == '0':
            state, flow = 0, 0.0
        elif key == '+':
            flow = min(250.0, flow + 20.0)
        elif key == '-':
            flow = max(0.0, flow - 20.0)
        elif key == 'q':
            break

        now = time.monotonic()
        if now - last_tx >= 0.15:
            last_tx = now
            frame += 1

            pkt = {
                "v": 1,
                "seq": frame,
                "dev": target_dev,
                "pump": pname.split()[0],
                "state": state,
                "flow": int(round(flow)),
                "max": 200,
                "rf": int(round((flow / 200.0) * 1000)),
                "lim": 0,
                "al": 2 if state == 4 else (1 if state == 3 else 0),
                "il": 0
            }

            send_packet(ser, pkt, target_dev)
            if not ser:
                print_pump_ascii_preview(pname, state, flow, frame)

        time.sleep(0.05)

    if ser:
        ser.close()


def main():
    parser = argparse.ArgumentParser(description="AVON AI Physical Pump Test Feeder")
    parser.add_argument("--port", help="Serial COM port (e.g. COM3)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    parser.add_argument("--device", type=int, default=1, choices=[1, 2, 3, 4, 5], help="Target Pump ID (1..5)")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive pump tester")
    args = parser.parse_args()

    run_interactive(args.port, args.baud, args.device)


if __name__ == "__main__":
    main()
