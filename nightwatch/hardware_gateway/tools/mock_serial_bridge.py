#!/usr/bin/env python3
"""
AVON AI - Mock Serial Loopback Bridge
Creates virtual serial interfaces or pipes telemetry to terminal windows
for end-to-end bench testing when physical Arduinos are not connected.
"""

import argparse
import json
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="AVON AI Mock Serial Monitor")
    parser.add_argument("--device", type=int, default=2, help="Device ID to monitor (1, 2, or 3)")
    args = parser.parse_args()

    print(f"=================================================")
    print(f" Monitoring Mock Serial Port for Arduino Device {args.device}")
    print(f" Waiting for packets from gateway bridge...")
    print(f"=================================================")

    # Read from standard input or socket
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                pkt = json.loads(line)
                dev = pkt.get("dev")
                if dev == args.device or args.device == 0:
                    flow = pkt.get("flow", 0.0)
                    lvl = pkt.get("lvl", 0.0)
                    alrm = pkt.get("alarm", 0)
                    print(f"[{time.strftime('%H:%M:%S')}] RECV Dev {dev}: flow={flow} bbl/hr | lvl={lvl} bbl | alarm={alrm}")
            except json.JSONDecodeError:
                pass
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
