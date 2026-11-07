#!/usr/bin/env python3
"""
AVON AI - Raspberry Pi 5 Hardware Gateway Bridge
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and dispatches real-time telemetry packets over USB Serial to the 3 Arduino UNO R4s.
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Gateway) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AvonGateway")


class ArduinoSerialManager:
    """Manages serial connections to the 3 Arduino UNO R4 nodes."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        self.baud = cfg.get("serial", {}).get("baud_rate", 115200)
        self.ports: Dict[int, Optional[Any]] = {1: None, 2: None, 3: None}
        self.port_paths: Dict[int, str] = {}
        self._init_port_paths()

    def _init_port_paths(self) -> None:
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("ports", {})
        )
        self.port_paths[1] = port_dict.get("device1", "COM3" if is_windows else "/dev/ttyACM0")
        self.port_paths[2] = port_dict.get("device2", "COM4" if is_windows else "/dev/ttyACM1")
        self.port_paths[3] = port_dict.get("device3", "COM5" if is_windows else "/dev/ttyACM2")

    def connect(self) -> None:
        if self.dry_run:
            logger.info("Running in DRY-RUN mode (hardware serial writes simulated).")
            return

        if not HAS_SERIAL:
            logger.warning("pyserial is not installed. Switching to dry-run mode.")
            self.dry_run = True
            return

        logger.info("Connecting to physical Arduino serial ports...")
        for dev_id, path in self.port_paths.items():
            try:
                ser = serial.Serial(path, self.baud, timeout=0.1)
                self.ports[dev_id] = ser
                logger.info(f"Connected to Device {dev_id} on {path} @ {self.baud} baud.")
            except Exception as e:
                logger.warning(f"Could not open port {path} for Device {dev_id}: {e}")
                self.ports[dev_id] = None

    def send_packet(self, dev_id: int, payload: dict) -> None:
        line = json.dumps(payload, separators=(',', ':')) + "\n"
        
        if self.dry_run:
            logger.debug(f"[MOCK TX -> Dev {dev_id}]: {line.strip()}")
            return

        ser = self.ports.get(dev_id)
        if ser is None or not ser.is_open:
            # Attempt lazy reconnect
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
        except Exception as e:
            logger.warning(f"Write error on Device {dev_id}: {e}")
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
    """Extracts device-specific payloads from the AVON AI simulation envelope."""

    def __init__(self, cfg: dict):
        self.t_cfg = cfg.get("telemetry", {})
        self.tank_id = self.t_cfg.get("tank_id", "T-104")
        self.duty_pump_id = self.t_cfg.get("duty_pump_id", "P-203")
        self.standby_pump_id = self.t_cfg.get("standby_pump_id", "P-204")
        self.pipeline_id = self.t_cfg.get("pipeline_id", "PL-1")
        self.treatment_id = self.t_cfg.get("treatment_id", "TRT-1")

    def _pump_state_code(self, run_state: str) -> int:
        mapping = {"STOPPED": 0, "RUNNING": 1, "TRIPPED": 2, "STARTING": 3}
        return mapping.get(run_state.upper(), 0)

    def extract_device1(self, state: dict) -> dict:
        """Extract Device 1 (Tank T-104 & Pumps P-203/P-204) payload."""
        tanks = state.get("tanks", {})
        pumps = state.get("pumps", {})
        
        t_data = tanks.get(self.tank_id, {})
        p203 = pumps.get(self.duty_pump_id, {})
        p204 = pumps.get(self.standby_pump_id, {})

        lvl = t_data.get("reported", t_data.get("volume", 0.0))
        cap = t_data.get("capacity", 1000.0)
        inflow = t_data.get("inflow", 0.0)
        outflow = t_data.get("outflow", 0.0)
        interlock_data = t_data.get("interlock", {})
        intlk_tripped = 1 if (isinstance(interlock_data, dict) and interlock_data.get("tripped")) else 0

        # Determine alarm level
        alarm_lvl = 0
        if lvl >= 950.0:
            alarm_lvl = 2 # HH
        elif lvl >= 900.0:
            alarm_lvl = 1 # H

        return {
            "dev": 1,
            "lvl": round(lvl, 1),
            "cap": round(cap, 1),
            "inflow": round(inflow, 1),
            "outflow": round(outflow, 1),
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
            "interlock": intlk_tripped
        }

    def extract_device2(self, state: dict) -> dict:
        """Extract Device 2 (Pipeline PL-1 Waterflow Visualizer) payload."""
        pipelines = state.get("pipelines", {})
        pl_data = pipelines.get(self.pipeline_id, {})

        flow = pl_data.get("flow", 0.0)
        cap = pl_data.get("cap", pl_data.get("max_flow", 250.0))
        rf = pl_data.get("restriction_factor", 1.0)
        alarm = 1 if rf < 0.98 else 0

        # Direction: 1 = forward, 0 = stopped, -1 = reverse
        direction = 1 if flow > 0.5 else 0

        return {
            "dev": 2,
            "flow": round(flow, 1),
            "cap": round(cap, 1),
            "restr": round(rf, 2),
            "dir": direction,
            "alarm": alarm
        }

    def extract_device3(self, state: dict) -> dict:
        """Extract Device 3 (Treatment Facility TRT-1 & Inflow Hub) payload."""
        treatment = state.get("treatment", {})
        tr_data = treatment.get(self.treatment_id, {})

        flow = tr_data.get("flow", 0.0)
        cap = tr_data.get("cap", tr_data.get("max_intake", 400.0))
        intake_f = tr_data.get("intake_factor", 1.0)
        alarm = 1 if intake_f < 0.98 else 0

        return {
            "dev": 3,
            "flow": round(flow, 1),
            "cap": round(cap, 1),
            "intake_factor": round(intake_f, 2),
            "alarm": alarm
        }


async def run_gateway(config_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    if verbose:
        logger.setLevel(logging.DEBUG)

    # Load configuration
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

    logger.info(f"Starting AVON AI Hardware Bridge...")
    logger.info(f"Target WebSocket: {ws_url}")
    logger.info("Waiting for simulation stream. Press Ctrl+C to stop.")

    while True:
        try:
            if not HAS_WEBSOCKETS:
                logger.error("The 'websockets' Python library is required. Install with: pip install websockets")
                await asyncio.sleep(5)
                continue

            async with websockets.connect(ws_url) as ws:
                logger.info(f"Successfully connected to AVON AI sim at {ws_url}")
                last_log_time = time.monotonic()
                tick_count = 0

                async for raw_msg in ws:
                    try:
                        data = json.loads(raw_msg)
                        state = data.get("state", {})
                        if not state:
                            continue

                        # Extract payloads for the 3 Arduinos
                        d1 = extractor.extract_device1(state)
                        d2 = extractor.extract_device2(state)
                        d3 = extractor.extract_device3(state)

                        # Dispatch over serial
                        serial_mgr.send_packet(1, d1)
                        serial_mgr.send_packet(2, d2)
                        serial_mgr.send_packet(3, d3)

                        tick_count += 1
                        now = time.monotonic()
                        if now - last_log_time >= 2.0:
                            logger.info(
                                f"Tick t={state.get('t_min')}m | "
                                f"T-104: {d1['lvl']} bbl | "
                                f"PL-1: {d2['flow']} bbl/hr (Dev2 FPS ~{int(d2['flow'])}) | "
                                f"TRT-1: {d3['flow']} bbl/hr"
                            )
                            last_log_time = now

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error processing sim tick: {e}")

        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Shutdown signal received.")
            break
        except Exception as e:
            logger.warning(f"WebSocket connection lost: {e}. Retrying in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)

    serial_mgr.close()


def main():
    parser = argparse.ArgumentParser(description="AVON AI Hardware Gateway Bridge (Raspberry Pi 5)")
    parser.add_argument("--config", default="hardware/gateway/config.json", help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate serial writes without physical Arduinos")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    try:
        asyncio.run(run_gateway(args.config, dry_run=args.dry_run, verbose=args.verbose))
    except KeyboardInterrupt:
        logger.info("Gateway stopped by operator.")


if __name__ == "__main__":
    main()
