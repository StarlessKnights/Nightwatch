#!/usr/bin/env python3
"""Replay protocol fixtures to one Arduino serial port. Requires pyserial."""
import argparse
import json
import time
from pathlib import Path

import serial

parser = argparse.ArgumentParser()
parser.add_argument("port")
parser.add_argument("--device", type=int, required=True, choices=(1, 2, 3))
parser.add_argument("--baud", type=int, default=115200)
parser.add_argument("--repeat", type=int, default=1)
parser.add_argument("--interval", type=float, default=0.2)
args = parser.parse_args()

fixture_path = Path(__file__).resolve().parents[1] / "protocol" / "examples.ndjson"
packets = [json.loads(row) for row in fixture_path.read_text().splitlines() if row.strip()]
packets = [packet for packet in packets if packet["dev"] == args.device]

with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=1) as port:
    time.sleep(2.0)  # USB serial opening can reset the UNO R4.
    for _ in range(args.repeat):
        for packet in packets:
            port.write((json.dumps(packet, separators=(",", ":")) + "\n").encode())
            port.flush()
            print(packet)
            time.sleep(args.interval)
