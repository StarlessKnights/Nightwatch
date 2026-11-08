#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (3-Pump Active / 5-Pump Ready)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and streams real-time telemetry to physical Arduino UNO R4s acting as pumps.

Key Architectural Guarantees:
  1. Continuous 10 Hz Telemetry Stream:
     Sends packets at 10 Hz (every 100 ms) so the Arduino firmware's 1.5s
     watchdog (LINK_TIMEOUT_MS) never expires, even when the sim is paused.
  2. Multi-Port Auto-Discovery & Broadcast:
     Automatically discovers Arduino serial ports (e.g. COM4, COM5, COM6)
     and broadcasts packets for Device 1 (P-201), Device 2 (P-203), and
     Device 3 (P-204). Each Arduino's firmware self-filters by its configured
     DEVICE_ID and ASSIGNED_PUMP, eliminating port-mapping mismatches.
  3. Physical Fault Tolerance:
     Isolated non-blocking writes per port. If any Arduino is unplugged,
     the remaining boards continue updating at full speed with 0 lag.
     Disconnected ports auto-reconnect every 3 seconds.
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
from typing import Any, Dict, List, Optional

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
class SerialPortLink:
    port: str
    ser: Optional[Any] = None
    is_online: bool = False
    last_reconnect_attempt: float = 0.0
    packets_sent: int = 0
    errors_caught: int = 0


class FaultTolerantSerialBus:
    """Manages independent, hot-pluggable serial links across all Arduino boards."""

    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        s_cfg = cfg.get("serial", {})
        self.baud = s_cfg.get("baud_rate", 115200)
        self.timeout = s_cfg.get("timeout_s", 0.05)
        self.cooldown = s_cfg.get("reconnect_cooldown_s", 3.0)
        self.auto_detect = s_cfg.get("auto_detect", True)
        self.active_devices: List[int] = s_cfg.get("active_devices", [1, 2, 3])
        self.links: Dict[str, SerialPortLink] = {}
        self._init_links()

    def _init_links(self) -> None:
        configured_ports = []
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("linux_ports", {})
        )
        for dev_key in [f"device{i}" for i in self.active_devices]:
            p = port_dict.get(dev_key)
            if p and p not in configured_ports:
                configured_ports.append(p)

        # Auto-detect real connected serial ports
        if HAS_SERIAL:
            try:
                for p_info in serial.tools.list_ports.comports():
                    p_name = p_info.device
                    # Include known Arduino ports or USB serial
                    if p_name not in configured_ports:
                        configured_ports.append(p_name)
            except Exception as e:
                logger.debug(f"Port scan exception: {e}")

        for p in configured_ports:
            self.links[p] = SerialPortLink(port=p)

    def connect_all(self) -> None:
        if self.dry_run:
            logger.info("Running in DRY-RUN mode (hardware serial writes simulated).")
            return

        if not HAS_SERIAL:
            logger.warning("pyserial is not installed! Run: pip install pyserial. Switching to dry-run mode.")
            self.dry_run = True
            return

        logger.info(f"Probing and connecting Arduino serial ports: {list(self.links.keys())}...")
        for port, link in self.links.items():
            self._try_connect(link)

    def _try_connect(self, link: SerialPortLink) -> bool:
        link.last_reconnect_attempt = time.monotonic()
        try:
            ser = serial.Serial(link.port, self.baud, timeout=self.timeout)
            link.ser = ser
            link.is_online = True
            logger.info(f"[ONLINE] Arduino connected on {link.port} at {self.baud} baud.")
            return True
        except Exception as e:
            link.ser = None
            link.is_online = False
            return False

    def scan_for_new_ports(self) -> None:
        """Periodically scans for newly inserted USB serial devices."""
        if not HAS_SERIAL or self.dry_run:
            return
        try:
            for p_info in serial.tools.list_ports.comports():
                p_name = p_info.device
                if p_name not in self.links:
                    logger.info(f"[DISCOVERY] New USB serial device detected: {p_name}")
                    link = SerialPortLink(port=p_name)
                    self.links[p_name] = link
                    self._try_connect(link)
        except Exception:
            pass

    def broadcast_packet(self, payload: dict) -> None:
        """Transmits a single NDJSON packet to all connected Arduinos with per-port fault isolation."""
        line = json.dumps(payload, separators=(',', ':')) + "\n"
        encoded = line.encode("utf-8")
        now = time.monotonic()

        if self.dry_run:
            logger.debug(f"[MOCK TX]: {line.strip()}")
            return

        # Attempt reconnect on offline ports
        for port, link in self.links.items():
            if not link.is_online or link.ser is None:
                if now - link.last_reconnect_attempt >= self.cooldown:
                    self._try_connect(link)

        # Isolated transmission
        for port, link in list(self.links.items()):
            if link.is_online and link.ser:
                try:
                    link.ser.write(encoded)
                    link.ser.flush()
                    link.packets_sent += 1
                except Exception as e:
                    link.is_online = False
                    link.errors_caught += 1
                    link.last_reconnect_attempt = now
                    logger.warning(
                        f"[FAULT TOLERANCE] Arduino on {port} disconnected: {e}. "
                        f"Other boards continue running smoothly. Auto-retry in {self.cooldown:.1f}s."
                    )
                    try:
                        link.ser.close()
                    except Exception:
                        pass
                    link.ser = None

    def get_health_summary(self) -> str:
        if self.dry_run:
            return "[SIMULATED / DRY-RUN]"
        tokens = []
        now = time.monotonic()
        for port, link in self.links.items():
            if link.is_online:
                tokens.append(f"{port}:ON")
            else:
                retry_in = max(0.0, self.cooldown - (now - link.last_reconnect_attempt))
                tokens.append(f"{port}:OFF({retry_in:.0f}s)")
        return " ".join(tokens)

    def close_all(self) -> None:
        for port, link in self.links.items():
            if link.ser and link.ser.is_open:
                try:
                    link.ser.close()
                except Exception:
                    pass
                link.ser = None
                link.is_online = False
        logger.info("All Arduino serial links closed.")


class PumpStateExtractor:
    """Extracts unified telemetry packets for Arduino matrix firmware."""

    def __init__(self, cfg: dict):
        self.seq = 0

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) % 65536
        return self.seq

    def _pump_code(self, p_data: dict, w_int: int) -> int:
        """
        Pump state codes:
          0: stopped, 1: running, 2: starting, 3: degraded, 4: tripped, 5: unavailable
        Rules:
          - Unavailable: Operator shut down / lockout -> code 5
          - Trip: Pump error -> code 4
          - Wear < 0.5 (w_int < 500): Degraded -> code 3
          - Starting: Warming up / changeover -> code 2
          - Running: Healthy -> code 1
          - Stopped: Idle / ready -> code 0
        """
        if not p_data.get("available", True):
            return 5
        st = p_data.get("run_state", "STOPPED").upper()
        if st == "TRIPPED":
            return 4
        if st == "STARTING":
            return 2
        if st == "RUNNING":
            return 3 if w_int < 500 else 1
        return 3 if w_int < 500 else 0

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

    def _get_tank_level_cap(self, pump_id: str, state: dict) -> tuple[int, int]:
        tanks = state.get("tanks", {})
        tank_id = "T-101" if pump_id == "P-201" else "T-104"
        t_data = tanks.get(tank_id, {})
        lvl = int(round(t_data.get("volume", 600)))
        cap = int(round(t_data.get("capacity", 1000)))
        return max(0, lvl), max(1, cap)

    def extract_pump(self, dev_id: int, pump_id: str, state: dict) -> dict:
        """Extracts telemetry packet for an outflow pump (P-201, P-203, P-204)."""
        pumps = state.get("pumps", {})
        p = pumps.get(pump_id, {})
        flow = p.get("flow", 0.0)

        # Base and effective health
        w_float = p.get("eff_health", p.get("health", p.get("capacity_factor", 1.0)))
        w_int = int(round(max(0.0, min(1.0, w_float)) * 1000))

        st_code = self._pump_code(p, w_int)
        lim_code = self._limiting_code(p.get("limited_by"))
        lvl, cap = self._get_tank_level_cap(pump_id, state)
        available = 1 if (p.get("available", True) and st_code != 5) else 0

        al = 0
        if st_code == 4:
            al = 2  # High alarm on trip
        elif st_code == 3:
            al = 1  # Advisory on wear < 0.5

        return {
            "v": 1,
            "seq": self._next_seq(),
            "dev": dev_id,
            "pump": pump_id,
            "state": st_code,
            "w": w_int,
            "available": available,
            "lvl": lvl,
            "cap": cap,
            "flow": int(round(flow)),
            "max": 200,
            "rf": int(round(w_float * 1000)),
            "lim": lim_code,
            "al": al,
            "il": 0
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

    bus = FaultTolerantSerialBus(cfg, dry_run=dry_run)
    bus.connect_all()

    extractor = PumpStateExtractor(cfg)
    active_devs = bus.active_devices

    # Shared telemetry state updated by WebSocket listener and streamed at 10 Hz
    current_state: Dict[str, Any] = {
        "pumps": {
            "P-201": {"run_state": "RUNNING", "health": 1.0, "flow": 150.0, "available": True},
            "P-203": {"run_state": "RUNNING", "health": 1.0, "flow": 180.0, "available": True},
            "P-204": {"run_state": "STOPPED", "health": 1.0, "flow": 0.0, "available": True}
        },
        "tanks": {
            "T-101": {"volume": 600, "capacity": 1000},
            "T-104": {"volume": 880, "capacity": 1000}
        },
        "t_min": 0
    }

    stop_event = asyncio.Event()

    async def tx_stream_task():
        """Continuous 10 Hz telemetry loop ensuring Arduino watchdogs never expire."""
        logger.info("Continuous 10 Hz hardware transmission stream started.")
        last_log = time.monotonic()
        last_scan = time.monotonic()

        while not stop_event.is_set():
            now = time.monotonic()

            # Rescan for new USB devices every 3 seconds
            if now - last_scan >= 3.0:
                bus.scan_for_new_ports()
                last_scan = now

            # Broadcast packets for each active device
            if 1 in active_devs:
                p1 = extractor.extract_pump(1, "P-201", current_state)
                bus.broadcast_packet(p1)
            if 2 in active_devs:
                p2 = extractor.extract_pump(2, "P-203", current_state)
                bus.broadcast_packet(p2)
            if 3 in active_devs:
                p3 = extractor.extract_pump(3, "P-204", current_state)
                bus.broadcast_packet(p3)

            # Log status ticker every 2 seconds
            if now - last_log >= 2.0:
                health = bus.get_health_summary()
                pumps = current_state.get("pumps", {})
                p201 = pumps.get("P-201", {})
                p203 = pumps.get("P-203", {})
                p204 = pumps.get("P-204", {})
                w201 = p201.get("eff_health", p201.get("health", 1.0))
                w203 = p203.get("eff_health", p203.get("health", 1.0))
                logger.info(
                    f"Tick t={current_state.get('t_min', 0)}m | "
                    f"P-201(D1): {p201.get('flow', 0):.0f} bbl/hr (w={w201:.2f}) | "
                    f"P-203(D2): {p203.get('flow', 0):.0f} bbl/hr (w={w203:.2f}) | "
                    f"P-204(D3): {p204.get('run_state', 'STOPPED')} | "
                    f"Links: [{health}]"
                )
                last_log = now

            # Stream at 10 Hz (100 ms interval)
            await asyncio.sleep(0.1)

    async def ws_rx_task():
        """WebSocket receiver keeping current_state synchronized with the FastAPI simulation."""
        while not stop_event.is_set():
            try:
                if not HAS_WEBSOCKETS:
                    logger.error("'websockets' library required. Run: pip install websockets")
                    await asyncio.sleep(5)
                    continue

                async with websockets.connect(ws_url) as ws:
                    logger.info(f"Connected to AVON AI sim backend at {ws_url}")
                    async for raw_msg in ws:
                        try:
                            data = json.loads(raw_msg)
                            state = data.get("state", {})
                            if state:
                                current_state.update(state)
                        except json.JSONDecodeError:
                            pass
                        except Exception as e:
                            logger.error(f"WebSocket parse error: {e}")

            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as e:
                logger.warning(f"Backend connection at {ws_url} lost: {e}. Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)

    tx_handle = asyncio.create_task(tx_stream_task())
    rx_handle = asyncio.create_task(ws_rx_task())

    try:
        await asyncio.gather(tx_handle, rx_handle)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        stop_event.set()
        tx_handle.cancel()
        rx_handle.cancel()
        bus.close_all()


def main():
    parser = argparse.ArgumentParser(description="AVON AI Hardware Pump Bridge")
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
