#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (5 Arduino Nodes)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and dispatches real-time telemetry packets over USB Serial to 5 Arduino UNO R4s.

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


class ArduinoSerialManager:
    """Manages serial connections to the 5 Arduino UNO R4 nodes."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        self.baud = cfg.get("serial", {}).get("baud_rate", 115200)
        self.ports: Dict[int, Optional[Any]] = {i: None for i in range(1, 6)}
        self.port_paths: Dict[int, str] = {}
        self._init_port_paths()

    def _init_port_paths(self) -> None:
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("linux_ports", {})
        )
        for i in range(1, 6):
            default_path = f"COM{i+2}" if is_windows else f"/dev/ttyACM{i-1}"
            self.port_paths[i] = port_dict.get(f"device{i}", default_path)

    def connect(self) -> None:
        if self.dry_run:
            logger.info("Running in DRY-RUN mode (hardware serial writes simulated).")
            return

        if not HAS_SERIAL:
            logger.warning("pyserial is not installed. Switching to dry-run mode.")
            self.dry_run = True
            return

        logger.info("Connecting to physical Arduino serial ports (5 devices)...")
        for dev_id, path in self.port_paths.items():
            try:
                ser = serial.Serial(path, self.baud, timeout=0.1)
                self.ports[dev_id] = ser
                logger.info(f"Connected to Device {dev_id} on {path} @ {self.baud} baud.")
            except Exception as e:
                logger.warning(f"Port {path} for Device {dev_id} not available: {e}")
                self.ports[dev_id] = None

    def send_packet(self, dev_id: int, payload: dict) -> None:
        line = json.dumps(payload, separators=(',', ':')) + "\n"
        
        if self.dry_run:
            logger.debug(f"[MOCK TX -> Dev {dev_id}]: {line.strip()}")
            return

        ser = self.ports.get(dev_id)
        if ser is None or not ser.is_open:
            try:
                path = self.port_paths[dev_id]
                self.ports[dev_id] = serial.Serial(path, self.baud, timeout=0.1)
                ser = self.ports[dev_id]
                logger.info(f"Reconnected to Device {dev_id} on {path}")
            except Exception:
                return

        try:
            ser.write(line.encode("utf-8"))
            ser.flush()
        except Exception:
            try:
                ser.close()
            except Exception:
                pass
            self.ports[dev_id] = None

    def close(self) -> None:
        for dev_id, ser in self.ports.items():
            if ser and ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass
        logger.info("All serial connections closed.")


class SimStateExtractor:
    """Extracts payloads for all 5 devices from the AVON AI simulation state."""

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

    def _pump_state_code(self, run_state: str) -> int:
        mapping = {"STOPPED": 0, "RUNNING": 1, "TRIPPED": 2, "STARTING": 3}
        return mapping.get(run_state.upper(), 0)

    def extract_device1(self, state: dict) -> dict:
        """Device 1: Tank T-104 & P-203/P-204."""
        tanks = state.get("tanks", {})
        pumps = state.get("pumps", {})
        t = tanks.get(self.t104_id, {})
        p203 = pumps.get(self.p203_id, {})
        p204 = pumps.get(self.p204_id, {})

        lvl = t.get("reported", t.get("volume", 0.0))
        alarm_lvl = 2 if lvl >= 950 else (1 if lvl >= 900 else 0)
        intlk = 1 if t.get("interlock", {}).get("tripped") else 0

        return {
            "dev": 1,
            "lvl": round(lvl, 1),
            "cap": round(t.get("capacity", 1000.0), 1),
            "inflow": round(t.get("inflow", 0.0), 1),
            "outflow": round(t.get("outflow", 0.0), 1),
            "p203": {
                "state": self._pump_state_code(p203.get("run_state", "STOPPED")),
                "cf": round(p203.get("eff_capacity_factor", p203.get("capacity_factor", 1.0)), 2),
                "label": p203.get("run_state", "STOPPED")
            },
            "p204": {
                "state": self._pump_state_code(p204.get("run_state", "STOPPED")),
                "cf": round(p204.get("eff_capacity_factor", p204.get("capacity_factor", 1.0)), 2),
                "label": p204.get("run_state", "STOPPED")
            },
            "alarm": alarm_lvl,
            "interlock": intlk
        }

    def extract_device2(self, state: dict) -> dict:
        """Device 2: Pipeline PL-1 (Upper Fluid Flow)."""
        pl = state.get("pipelines", {}).get(self.pl1_id, {})
        flow = pl.get("flow", 0.0)
        rf = pl.get("restriction_factor", 1.0)
        return {
            "dev": 2,
            "flow": round(flow, 1),
            "cap": round(pl.get("cap", pl.get("max_flow", 250.0)), 1),
            "restr": round(rf, 2),
            "dir": 1 if flow > 0.5 else 0,
            "alarm": 1 if rf < 0.98 else 0
        }

    def extract_device3(self, state: dict) -> dict:
        """Device 3: Treatment Facility TRT-1."""
        tr = state.get("treatment", {}).get(self.trt_id, {})
        flow = tr.get("flow", 0.0)
        intake_f = tr.get("intake_factor", 1.0)
        return {
            "dev": 3,
            "flow": round(flow, 1),
            "cap": round(tr.get("cap", tr.get("max_intake", 400.0)), 1),
            "intake_factor": round(intake_f, 2),
            "alarm": 1 if intake_f < 0.98 else 0
        }

    def extract_device4(self, state: dict) -> dict:
        """Device 4: Tank T-101 & P-201."""
        t = state.get("tanks", {}).get(self.t101_id, {})
        p201 = state.get("pumps", {}).get(self.p201_id, {})
        lvl = t.get("reported", t.get("volume", 0.0))
        alarm_lvl = 2 if lvl >= 950 else (1 if lvl >= 900 else 0)
        intlk = 1 if t.get("interlock", {}).get("tripped") else 0

        return {
            "dev": 4,
            "lvl": round(lvl, 1),
            "cap": round(t.get("capacity", 1000.0), 1),
            "inflow": round(t.get("inflow", 0.0), 1),
            "outflow": round(t.get("outflow", 0.0), 1),
            "p201": {
                "state": self._pump_state_code(p201.get("run_state", "STOPPED")),
                "cf": round(p201.get("eff_capacity_factor", p201.get("capacity_factor", 1.0)), 2),
                "label": p201.get("run_state", "STOPPED")
            },
            "alarm": alarm_lvl,
            "interlock": intlk
        }

    def extract_device5(self, state: dict) -> dict:
        """Device 5: Pipeline PL-2 (Lower Fluid Flow)."""
        pl = state.get("pipelines", {}).get(self.pl2_id, {})
        flow = pl.get("flow", 0.0)
        rf = pl.get("restriction_factor", 1.0)
        return {
            "dev": 5,
            "flow": round(flow, 1),
            "cap": round(pl.get("cap", pl.get("max_flow", 250.0)), 1),
            "restr": round(rf, 2),
            "dir": 1 if flow > 0.5 else 0,
            "alarm": 1 if rf < 0.98 else 0
        }


async def run_gateway(config_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    if verbose:
        logger.setLevel(logging.DEBUG)

    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ws_url = cfg.get("backend", {}).get("ws_url", "ws://127.0.0.1:8000/ws/sim")
    reconnect_delay = cfg.get("backend", {}).get("reconnect_interval_s", 2.0)

    serial_mgr = ArduinoSerialManager(cfg, dry_run=dry_run)
    serial_mgr.connect()

    extractor = SimStateExtractor(cfg)

    logger.info("Starting AVON AI 5-Node Hardware Gateway Bridge...")
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

                        # Extract for all 5 devices
                        d1 = extractor.extract_device1(state)
                        d2 = extractor.extract_device2(state)
                        d3 = extractor.extract_device3(state)
                        d4 = extractor.extract_device4(state)
                        d5 = extractor.extract_device5(state)

                        # Send to each Arduino
                        serial_mgr.send_packet(1, d1)
                        serial_mgr.send_packet(2, d2)
                        serial_mgr.send_packet(3, d3)
                        serial_mgr.send_packet(4, d4)
                        serial_mgr.send_packet(5, d5)

                        now = time.monotonic()
                        if now - last_log_time >= 2.0:
                            logger.info(
                                f"Tick t={state.get('t_min')}m | "
                                f"T-104: {d1['lvl']} bbl | PL-1: {d2['flow']} bbl/hr | "
                                f"TRT-1: {d3['flow']} bbl/hr | "
                                f"T-101: {d4['lvl']} bbl | PL-2: {d5['flow']} bbl/hr"
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

    serial_mgr.close()


def main():
    parser = argparse.ArgumentParser(description="AVON AI 5-Node Hardware Gateway Bridge")
    parser.add_argument("--config", default="hardware/gateway/config.json", help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate serial writes without hardware Arduinos")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    try:
        asyncio.run(run_gateway(args.config, dry_run=args.dry_run, verbose=args.verbose))
    except KeyboardInterrupt:
        logger.info("Gateway stopped by operator.")


if __name__ == "__main__":
    main()
