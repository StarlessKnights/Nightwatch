#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (5-Pump Visualizer Network)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and streams real-time telemetry to 5 Arduino UNO R4s acting as physical pumps.

Pump Assignment:
  Device 1: Pump P-203 (Duty Pump on Tank T-104 -> PL-1)
  Device 2: Pump P-204 (Standby Pump on Tank T-104 -> PL-1)
  Device 3: Pump P-201 (Duty Pump on Tank T-101 -> PL-2)
  Device 4: Pump P-SRC1 (Wellhead Inflow Lift Pump -> T-104)
  Device 5: Pump P-SRC2 (Wellhead Inflow Lift Pump -> T-101)

Physical Fault Tolerance:
  - Each Arduino serial channel has independent write isolation.
  - If any Arduino is unplugged, the remaining 4 pumps continue running uninterrupted.
  - Automatic non-blocking hot-plug reconnect when re-plugged.
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
class PumpChannel:
    dev_id: int
    pump_id: str
    name: str
    port_path: str
    ser: Optional[Any] = None
    is_online: bool = False
    last_reconnect_attempt: float = 0.0
    reconnect_cooldown_s: float = 3.0
    packets_sent: int = 0
    errors_caught: int = 0


class FaultTolerantPumpManager:
    """Manages 5 independent serial links for the 5 physical pump nodes."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        s_cfg = cfg.get("serial", {})
        self.baud = s_cfg.get("baud_rate", 115200)
        self.timeout = s_cfg.get("timeout_s", 0.05)
        self.cooldown = s_cfg.get("reconnect_cooldown_s", 3.0)
        self.channels: Dict[int, PumpChannel] = {}
        self._init_channels()

    def _init_channels(self) -> None:
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("linux_ports", {})
        )
        pumps_cfg = self.cfg.get("pumps", {})
        for i in range(1, 6):
            p_info = pumps_cfg.get(f"device{i}", {})
            pid = p_info.get("id", f"P-{i}")
            pname = p_info.get("name", f"Pump {i}")
            default_path = f"COM{i+2}" if is_windows else f"/dev/ttyACM{i-1}"
            path = port_dict.get(f"device{i}", default_path)
            self.channels[i] = PumpChannel(
                dev_id=i,
                pump_id=pid,
                name=pname,
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

        logger.info("Connecting to physical Arduino serial ports (5 pumps)...")
        for dev_id, ch in self.channels.items():
            self._try_connect(ch)

    def _try_connect(self, ch: PumpChannel) -> bool:
        ch.last_reconnect_attempt = time.monotonic()
        try:
            ser = serial.Serial(ch.port_path, self.baud, timeout=self.timeout)
            ch.ser = ser
            ch.is_online = True
            logger.info(f"[ONLINE] Device {ch.dev_id} ({ch.name}) connected on {ch.port_path}.")
            return True
        except Exception:
            ch.ser = None
            ch.is_online = False
            return False

    def send_packet(self, dev_id: int, payload: dict) -> None:
        ch = self.channels.get(dev_id)
        if not ch:
            return

        line = json.dumps(payload, separators=(',', ':')) + "\n"
        now = time.monotonic()

        if self.dry_run:
            logger.debug(f"[MOCK TX -> Dev {dev_id} ({ch.pump_id})]: {line.strip()}")
            return

        # Attempt reconnect if offline and cooldown passed
        if not ch.is_online or ch.ser is None or not ch.ser.is_open:
            if now - ch.last_reconnect_attempt >= ch.reconnect_cooldown_s:
                if not self._try_connect(ch):
                    return
            else:
                return

        # Isolated write
        try:
            ch.ser.write(line.encode("utf-8"))
            ch.ser.flush()
            ch.packets_sent += 1
        except Exception as e:
            ch.errors_caught += 1
            ch.is_online = False
            logger.warning(
                f"[FAULT TOLERANCE] Device {dev_id} ({ch.name}) on {ch.port_path} disconnected: {e}. "
                f"Remaining pumps continue running smoothly. Will retry in {ch.reconnect_cooldown_s:.1f}s."
            )
            try:
                ch.ser.close()
            except Exception:
                pass
            ch.ser = None
            ch.last_reconnect_attempt = now

    def get_health_summary(self) -> str:
        if self.dry_run:
            return "[SIMULATED / DRY-RUN]"
        tokens = []
        now = time.monotonic()
        for i in range(1, 6):
            ch = self.channels[i]
            if ch.is_online:
                tokens.append(f"{ch.pump_id}:ON")
            else:
                retry_in = max(0.0, ch.reconnect_cooldown_s - (now - ch.last_reconnect_attempt))
                tokens.append(f"{ch.pump_id}:OFF({retry_in:.0f}s)")
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
        logger.info("All pump serial links closed.")


class PumpStateExtractor:
    """Extracts state for all 5 physical pumps from simulation telemetry."""

    def __init__(self, cfg: dict):
        self.seq = 0

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) % 65536
        return self.seq

    def _pump_code(self, p_data: dict) -> int:
        """0: stopped, 1: running, 2: starting, 3: degraded, 4: tripped, 5: unavailable"""
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

    def extract_pump(self, dev_id: int, pump_id: str, state: dict) -> dict:
        """Extracts telemetry packet for an outflow pump (P-203, P-204, P-201)."""
        pumps = state.get("pumps", {})
        p = pumps.get(pump_id, {})
        flow = p.get("flow", 0.0)
        cf = p.get("eff_capacity_factor", p.get("capacity_factor", 1.0))
        st_code = self._pump_code(p)
        lim_code = self._limiting_code(p.get("limited_by"))

        # Determine alarm level
        al = 0
        if st_code == 4:  # Tripped
            al = 2
        elif st_code == 3:  # Degraded
            al = 1

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": dev_id,
            "pump": pump_id,
            "state": st_code,
            "flow": int(round(flow)),
            "max": 200,
            "rf": int(round(cf * 1000)),
            "lim": lim_code,
            "al": al,
            "il": 0
        }

    def extract_inflow_pump(self, dev_id: int, source_id: str, feeds_tank: str, state: dict) -> dict:
        """Extracts telemetry packet for a wellhead inflow pump (P-SRC1, P-SRC2)."""
        sources = state.get("sources", {})
        tanks = state.get("tanks", {})
        src = sources.get(source_id, {})
        t = tanks.get(feeds_tank, {})

        is_shut_in = src.get("shut_in", False) or t.get("interlock", {}).get("tripped", False)
        rate = src.get("flow", 0.0) if not is_shut_in else 0.0
        curtail_pct = src.get("curtailment_pct", 0.0)

        # State mapping for inflow pump
        if is_shut_in:
            st_code = 4  # Tripped / Shut in by interlock
            al = 3       # Critical HH alarm
        elif curtail_pct > 5.0:
            st_code = 3  # Degraded / curtailed
            al = 1
        elif rate > 0.0:
            st_code = 1  # Running
            al = 0
        else:
            st_code = 0  # Stopped
            al = 0

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": dev_id,
            "pump": f"P-{source_id}",
            "state": st_code,
            "flow": int(round(rate)),
            "max": int(src.get("rate", 180)),
            "rf": int(round((1.0 - curtail_pct / 100.0) * 1000)),
            "lim": 0,
            "al": al,
            "il": 1 if is_shut_in else 0
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

    pump_mgr = FaultTolerantPumpManager(cfg, dry_run=dry_run)
    pump_mgr.connect_all()

    extractor = PumpStateExtractor(cfg)

    logger.info("Starting AVON AI 5-Pump Hardware Bridge...")
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

                        # Extract packets for all 5 physical pumps
                        p1 = extractor.extract_pump(1, "P-203", state)
                        p2 = extractor.extract_pump(2, "P-204", state)
                        p3 = extractor.extract_pump(3, "P-201", state)
                        p4 = extractor.extract_inflow_pump(4, "SRC-1", "T-104", state)
                        p5 = extractor.extract_inflow_pump(5, "SRC-2", "T-101", state)

                        # Send to each Arduino pump node independently
                        pump_mgr.send_packet(1, p1)
                        pump_mgr.send_packet(2, p2)
                        pump_mgr.send_packet(3, p3)
                        pump_mgr.send_packet(4, p4)
                        pump_mgr.send_packet(5, p5)

                        now = time.monotonic()
                        if now - last_log_time >= 2.0:
                            health = pump_mgr.get_health_summary()
                            logger.info(
                                f"Tick t={state.get('t_min')}m | "
                                f"P-203: {p1['flow']} bbl/hr (st={p1['state']}) | "
                                f"P-204: {p2['flow']} bbl/hr (st={p2['state']}) | "
                                f"P-201: {p3['flow']} bbl/hr (st={p3['state']}) | "
                                f"Pumps: [{health}]"
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

    pump_mgr.close_all()


def main():
    parser = argparse.ArgumentParser(description="AVON AI 5-Pump Hardware Bridge")
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
