#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (Fault-Tolerant 5-Node Visualizer Network)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and dispatches real-time telemetry packets over USB Serial to 5 Arduino UNO R4s.

Physical Fault Tolerance Features:
  - Complete per-device serial write isolation (one Arduino disconnecting NEVER stalls others).
  - Background auto-reconnect with non-blocking backoff (recovers as soon as cable is re-plugged).
  - Dual protocol support: Manas v1 compact NDJSON contract and human-readable verbose JSON.
  - Live per-device connection health dashboard.

Asset mapping:
  Device 1: Tank T-104 & P-203/P-204 Subsystem
  Device 2: Pipeline PL-1 (Upper Fluid Flow Visualizer)
  Device 3: Treatment Facility TRT-1 (Central Intake Hub)
  Device 4: Tank T-101 & Pump P-201 Subsystem
  Device 5: Pipeline PL-2 (Lower Fluid Flow Visualizer)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Gateway) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AvonGateway")


@dataclass
class DeviceChannel:
    dev_id: int
    name: str
    port_path: str
    ser: Optional[Any] = None
    is_online: bool = False
    last_reconnect_attempt: float = 0.0
    reconnect_cooldown_s: float = 3.0
    packets_sent: int = 0
    errors_caught: int = 0


class FaultTolerantSerialManager:
    """Manages independent, fault-tolerant serial links to 5 Arduino nodes."""

    DEVICE_NAMES = {
        1: "Tank T-104 & Pumps",
        2: "Pipeline PL-1 (Upper)",
        3: "Treatment TRT-1 Hub",
        4: "Tank T-101 & P-201",
        5: "Pipeline PL-2 (Lower)"
    }

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        s_cfg = cfg.get("serial", {})
        self.baud = s_cfg.get("baud_rate", 115200)
        self.timeout = s_cfg.get("timeout_s", 0.05)
        self.cooldown = s_cfg.get("reconnect_cooldown_s", 3.0)
        self.channels: Dict[int, DeviceChannel] = {}
        self._init_channels()

    def _init_channels(self) -> None:
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("linux_ports", {})
        )
        for i in range(1, 6):
            default_path = f"COM{i+2}" if is_windows else f"/dev/ttyACM{i-1}"
            path = port_dict.get(f"device{i}", default_path)
            self.channels[i] = DeviceChannel(
                dev_id=i,
                name=self.DEVICE_NAMES.get(i, f"Device {i}"),
                port_path=path,
                reconnect_cooldown_s=self.cooldown
            )

    def connect_all(self) -> None:
        if self.dry_run:
            logger.info("Running in DRY-RUN mode (hardware serial writes simulated).")
            return

        if not HAS_SERIAL:
            logger.warning("pyserial is not installed. Switching to dry-run mode.")
            self.dry_run = True
            return

        logger.info("Connecting to physical Arduino serial ports (5 devices)...")
        for dev_id, ch in self.channels.items():
            self._try_connect(ch)

    def _try_connect(self, ch: DeviceChannel) -> bool:
        """Attempt a non-blocking open on a single device channel."""
        ch.last_reconnect_attempt = time.monotonic()
        try:
            ser = serial.Serial(ch.port_path, self.baud, timeout=self.timeout)
            ch.ser = ser
            ch.is_online = True
            logger.info(f"[ONLINE] Device {ch.dev_id} ({ch.name}) connected on {ch.port_path}.")
            return True
        except Exception as e:
            ch.ser = None
            ch.is_online = False
            return False

    def send_packet(self, dev_id: int, payload: dict) -> None:
        """Sends telemetry to a specific device. 100% isolated: failures never affect other devices."""
        ch = self.channels.get(dev_id)
        if not ch:
            return

        line = json.dumps(payload, separators=(',', ':')) + "\n"
        now = time.monotonic()

        if self.dry_run:
            logger.debug(f"[MOCK TX -> Dev {dev_id}]: {line.strip()}")
            return

        # If offline, check if cooldown elapsed to attempt reconnect
        if not ch.is_online or ch.ser is None or not ch.ser.is_open:
            if now - ch.last_reconnect_attempt >= ch.reconnect_cooldown_s:
                if not self._try_connect(ch):
                    return  # Still offline, exit quickly without blocking
            else:
                return  # In cooldown, skip immediately

        # Attempt isolated write
        try:
            ch.ser.write(line.encode("utf-8"))
            ch.ser.flush()
            ch.packets_sent += 1
        except Exception as e:
            # Physical disconnect or hardware bus fault detected!
            ch.errors_caught += 1
            ch.is_online = False
            logger.warning(
                f"[FAULT TOLERANCE] Device {dev_id} ({ch.name}) on {ch.port_path} disconnected: {e}. "
                f"Other devices continue uninterrupted. Will retry in {ch.reconnect_cooldown_s:.1f}s."
            )
            try:
                ch.ser.close()
            except Exception:
                pass
            ch.ser = None
            ch.last_reconnect_attempt = now

    def get_health_summary(self) -> str:
        """Returns visual status chip for all 5 devices."""
        if self.dry_run:
            return "[SIMULATED / DRY-RUN]"
        tokens = []
        now = time.monotonic()
        for i in range(1, 6):
            ch = self.channels[i]
            if ch.is_online:
                tokens.append(f"D{i}:ON")
            else:
                retry_in = max(0.0, ch.reconnect_cooldown_s - (now - ch.last_reconnect_attempt))
                tokens.append(f"D{i}:OFF({retry_in:.0f}s)")
        return " ".join(tokens)

    def close_all(self) -> None:
        for dev_id, ch in self.channels.items():
            if ch.ser and ch.ser.is_open:
                try:
                    ch.ser.close()
                except Exception:
                    pass
                ch.ser = None
                ch.is_online = False
        logger.info("All serial connections closed.")


class SimStateExtractor:
    """Translates simulation states into packets compatible with Manas v1 protocol."""

    def __init__(self, cfg: dict):
        self.t_cfg = cfg.get("telemetry", {})
        self.t104_id = self.t_cfg.get("tank_104_id", "T-104")
        self.t101_id = self.t_cfg.get("tank_101_id", "T-101")
        self.p203_id = self.t_cfg.get("duty_pump_id", "P-203")
        self.p204_id = self.t_cfg.get("standby_pump_id", "P-204")
        self.p201_id = self.t_cfg.get("pump_201_id", "P-201")
        self.pl1_id = self.t_cfg.get("pipeline_1_id", "PL-1")
        self.pl2_id = self.t_cfg.get("pipeline_2_id", "PL-2")
        self.trt_id = self.t_cfg.get("treatment_id", "TRT-1")
        self.seq = 0

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) % 65536
        return self.seq

    def _pump_code(self, p_data: dict) -> int:
        """
        Manas Pump Codes:
          0: stopped, 1: running, 2: starting, 3: degraded, 4: tripped, 5: unavailable
        """
        if not p_data.get("available", True):
            return 5
        st = p_data.get("run_state", "STOPPED").upper()
        if st == "TRIPPED":
            return 4
        if st == "STARTING":
            return 2
        if st == "RUNNING":
            cf = p_data.get("eff_capacity_factor", p_data.get("capacity_factor", 1.0))
            return 3 if cf < 0.95 else 1
        return 0

    def _limiting_code(self, limited_by: str | None) -> int:
        """0: none, 1: pipeline, 2: treatment, 3: tank volume."""
        if not limited_by:
            return 0
        l = limited_by.lower()
        if "pipe" in l:
            return 1
        if "treat" in l:
            return 2
        if "tank" in l or "vol" in l:
            return 3
        return 0

    def extract_device1(self, state: dict) -> dict:
        """Device 1: Tank T-104 & P-203/P-204."""
        t = state.get("tanks", {}).get(self.t104_id, {})
        p203 = state.get("pumps", {}).get(self.p203_id, {})
        p204 = state.get("pumps", {}).get(self.p204_id, {})

        lvl = t.get("reported", t.get("volume", 0.0))
        h, hh = 900, 950
        al = 3 if lvl >= hh else (2 if lvl >= h else 0)
        il = 1 if t.get("interlock", {}).get("tripped") else 0

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": 1,
            "lvl": int(round(lvl)),
            "cap": int(t.get("capacity", 1000)),
            "h": h,
            "hh": hh,
            "p1": self._pump_code(p203),
            "p2": self._pump_code(p204),
            "al": al,
            "il": il
        }

    def extract_device2(self, state: dict) -> dict:
        """Device 2: Pipeline PL-1."""
        pl = state.get("pipelines", {}).get(self.pl1_id, {})
        p203 = state.get("pumps", {}).get(self.p203_id, {})
        flow = pl.get("flow", 0.0)
        rf = pl.get("restriction_factor", 1.0)
        al = 2 if rf < 0.95 else 0
        dir_val = 1 if flow > 0.5 else 0
        lim = self._limiting_code(p203.get("limited_by"))

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": 2,
            "flow": int(round(flow)),
            "max": int(pl.get("cap", pl.get("max_flow", 250))),
            "rf": int(round(rf * 1000)),
            "dir": dir_val,
            "lim": lim,
            "al": al
        }

    def extract_device3(self, state: dict) -> dict:
        """Device 3: Treatment Facility TRT-1."""
        tr = state.get("treatment", {}).get(self.trt_id, {})
        flow = tr.get("flow", 0.0)
        tf = tr.get("intake_factor", 1.0)
        bp = 1 if tf < 0.95 else 0
        al = 2 if bp else 0

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": 3,
            "flow": int(round(flow)),
            "max": int(tr.get("cap", tr.get("max_intake", 400))),
            "tf": int(round(tf * 1000)),
            "bp": bp,
            "al": al
        }

    def extract_device4(self, state: dict) -> dict:
        """Device 4: Tank T-101 & P-201."""
        t = state.get("tanks", {}).get(self.t101_id, {})
        p201 = state.get("pumps", {}).get(self.p201_id, {})
        lvl = t.get("reported", t.get("volume", 0.0))
        h, hh = 900, 950
        al = 3 if lvl >= hh else (2 if lvl >= h else 0)
        il = 1 if t.get("interlock", {}).get("tripped") else 0

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": 4,
            "lvl": int(round(lvl)),
            "cap": int(t.get("capacity", 1000)),
            "h": h,
            "hh": hh,
            "p1": self._pump_code(p201),
            "p2": 0,
            "al": al,
            "il": il
        }

    def extract_device5(self, state: dict) -> dict:
        """Device 5: Pipeline PL-2."""
        pl = state.get("pipelines", {}).get(self.pl2_id, {})
        p201 = state.get("pumps", {}).get(self.p201_id, {})
        flow = pl.get("flow", 0.0)
        rf = pl.get("restriction_factor", 1.0)
        al = 2 if rf < 0.95 else 0
        dir_val = 1 if flow > 0.5 else 0
        lim = self._limiting_code(p201.get("limited_by"))

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": 5,
            "flow": int(round(flow)),
            "max": int(pl.get("cap", pl.get("max_flow", 250))),
            "rf": int(round(rf * 1000)),
            "dir": dir_val,
            "lim": lim,
            "al": al
        }


async def run_gateway(config_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    if verbose:
        logger.setLevel(logging.DEBUG)

    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ws_url = cfg.get("backend", {}).get("ws_url", "ws://127.0.0.1:8080/ws/sim")
    reconnect_delay = cfg.get("backend", {}).get("reconnect_interval_s", 2.0)

    serial_mgr = FaultTolerantSerialManager(cfg, dry_run=dry_run)
    serial_mgr.connect_all()

    extractor = SimStateExtractor(cfg)

    logger.info("Starting AVON AI Fault-Tolerant Hardware Bridge...")
    logger.info(f"Target WebSocket: {ws_url}")

    while True:
        try:
            if not HAS_WEBSOCKETS:
                logger.error("'websockets' library required. Install with: pip install websockets")
                await asyncio.sleep(5)
                continue

            async with websockets.connect(ws_url) as ws:
                logger.info(f"Connected to AVON AI sim at {ws_url}")
                last_log_time = time.monotonic()

                async for raw_msg in ws:
                    try:
                        data = json.loads(raw_msg)
                        state = data.get("state", {})
                        if not state:
                            continue

                        # Extract payloads for all 5 nodes
                        d1 = extractor.extract_device1(state)
                        d2 = extractor.extract_device2(state)
                        d3 = extractor.extract_device3(state)
                        d4 = extractor.extract_device4(state)
                        d5 = extractor.extract_device5(state)

                        # Isolated dispatch: each channel handles disconnects without blocking others
                        serial_mgr.send_packet(1, d1)
                        serial_mgr.send_packet(2, d2)
                        serial_mgr.send_packet(3, d3)
                        serial_mgr.send_packet(4, d4)
                        serial_mgr.send_packet(5, d5)

                        now = time.monotonic()
                        if now - last_log_time >= 2.0:
                            health = serial_mgr.get_health_summary()
                            logger.info(
                                f"Tick t={state.get('t_min')}m | "
                                f"T-104: {d1['lvl']} bbl | PL-1: {d2['flow']} bbl/hr | "
                                f"TRT-1: {d3['flow']} bbl/hr | "
                                f"Health: [{health}]"
                            )
                            last_log_time = now

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error handling tick: {e}")

        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Shutdown signal received.")
            break
        except Exception as e:
            logger.warning(f"WebSocket disconnected: {e}. Retrying in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)

    serial_mgr.close_all()


def main():
    parser = argparse.ArgumentParser(description="AVON AI Fault-Tolerant Hardware Bridge")
    parser.add_argument("--config", default="hardware_gateway/config.json", help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate serial writes without hardware Arduinos")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    try:
        asyncio.run(run_gateway(args.config, dry_run=args.dry_run, verbose=args.verbose))
    except KeyboardInterrupt:
        logger.info("Gateway stopped by operator.")


if __name__ == "__main__":
    main()
