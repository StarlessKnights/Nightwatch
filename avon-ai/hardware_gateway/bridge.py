#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (3-Pump Active / 5-Pump Ready)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and streams real-time telemetry to physical Arduino UNO R4s acting as pumps.
Also ingests upstream hardware telemetry (knob wear control, casing thermal sensors,
light sensors, buzzer alarms) and relays physical connect/disconnect state to the backend.

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
     Isolated non-blocking writes and reads per port. If any Arduino is unplugged,
     the remaining boards continue updating at full speed with 0 lag.
     Disconnected ports auto-reconnect every 3 seconds.
  4. Real-time Presence & Sensor Coupling:
     Connecting an Arduino immediately notifies the backend to make its assigned
     pump available and running. Disconnecting an Arduino immediately locks out
     availability and triggers industrial standby changeover. Upstream knob and
     thermal sensor readings feed the live simulation state.
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
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

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

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

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
    device_id: Optional[int] = None


PUMPS = {1: "P-201", 2: "P-203", 3: "P-204"}
HELLO = re.compile(r"^AVON\|HELLO\|v=1\|dev=([1-3])(?:\|pump=[^|]+)?\|profile=pump\|fw=")


def parse_hello(line: str) -> Optional[int]:
    match = HELLO.match(line.strip())
    return int(match.group(1)) if match else None


class FaultTolerantSerialBus:
    """Manages independent, hot-pluggable serial links across all Arduino boards."""

    def __init__(
        self,
        cfg: dict,
        dry_run: bool = False,
        on_presence_change: Optional[Callable[[int, bool], None]] = None
    ):
        self.cfg = cfg
        self.dry_run = dry_run or not HAS_SERIAL
        s_cfg = cfg.get("serial", {})
        self.baud = s_cfg.get("baud_rate", 115200)
        self.timeout = s_cfg.get("timeout_s", 0.05)
        self.cooldown = s_cfg.get("reconnect_cooldown_s", 3.0)
        self.auto_detect = s_cfg.get("auto_detect", True)
        self.active_devices: List[int] = s_cfg.get("active_devices", [1, 2, 3])
        self.on_presence_change = on_presence_change
        self.links: Dict[str, SerialPortLink] = {}
        self._init_links()

    def _init_links(self) -> None:
        configured_ports = []
        is_windows = platform.system() == "Windows"
        port_dict = (
            self.cfg.get("serial", {}).get("windows_ports", {})
            if is_windows
            else self.cfg.get("serial", {}).get("macos_ports" if platform.system() == "Darwin" else "linux_ports", {})
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
                    if (p_info.vid == 0x2341 or "usbmodem" in p_name.lower() or "ttyacm" in p_name.lower()) and p_name not in configured_ports:
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

    def _disconnect_link(self, link: SerialPortLink, reason: str = "") -> None:
        old_dev = link.device_id
        link.is_online = False
        link.device_id = None
        link.errors_caught += 1
        link.last_reconnect_attempt = time.monotonic()
        if link.ser:
            try:
                link.ser.close()
            except Exception:
                pass
            link.ser = None

        logger.warning(
            f"[FAULT TOLERANCE] Arduino on {link.port} disconnected{f': {reason}' if reason else ''}. "
            f"Other boards continue running smoothly. Auto-retry in {self.cooldown:.1f}s."
        )

        if old_dev and self.on_presence_change:
            try:
                self.on_presence_change(old_dev, False)
            except Exception as e:
                logger.debug(f"Presence change callback error: {e}")

    def _try_connect(self, link: SerialPortLink) -> bool:
        link.last_reconnect_attempt = time.monotonic()
        try:
            ser = serial.Serial(link.port, self.baud, timeout=0.1)
            deadline = time.monotonic() + 2.5
            next_probe = 0.0
            device_id = None

            # First, check if the MCU already emitted HELLO banner on startup
            try:
                line = ser.readline().decode("utf-8", errors="replace")
                device_id = parse_hello(line)
            except Exception:
                pass

            # Otherwise actively probe with AVON|IDENTIFY
            while not device_id and time.monotonic() < deadline:
                if time.monotonic() >= next_probe:
                    ser.write(b"AVON|IDENTIFY\n")
                    ser.flush()
                    next_probe = time.monotonic() + 0.4
                try:
                    line = ser.readline().decode("utf-8", errors="replace")
                    device_id = parse_hello(line)
                except Exception:
                    pass

            if device_id not in self.active_devices or any(
                other.is_online and other.device_id == device_id
                for other in self.links.values()
                if other is not link
            ):
                ser.close()
                return False

            link.ser = ser
            link.device_id = device_id
            link.is_online = True
            logger.info(f"[ONLINE] Device {device_id} ({PUMPS[device_id]}) on {link.port}.")

            if self.on_presence_change:
                try:
                    self.on_presence_change(device_id, True)
                except Exception as e:
                    logger.debug(f"Presence change callback error: {e}")

            return True
        except Exception:
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
                if (p_info.vid == 0x2341 or "usbmodem" in p_name.lower() or "ttyacm" in p_name.lower()) and p_name not in self.links:
                    logger.info(f"[DISCOVERY] New USB serial device detected: {p_name}")
                    link = SerialPortLink(port=p_name)
                    self.links[p_name] = link
                    self._try_connect(link)
        except Exception:
            pass

    def broadcast_packet(self, payload: dict) -> None:
        """Transmit only to the Arduino identified by the packet device ID."""
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
            if link.is_online and link.ser and link.device_id == payload.get("dev"):
                try:
                    link.ser.write(encoded)
                    link.ser.flush()
                    link.packets_sent += 1
                except Exception as e:
                    self._disconnect_link(link, str(e))

    def read_upstream_telemetry(self) -> List[dict]:
        """Reads incoming NDJSON telemetry lines from all connected microcontrollers."""
        if self.dry_run or not HAS_SERIAL:
            return []

        packets = []
        for port, link in list(self.links.items()):
            if not link.is_online or not link.ser:
                continue
            try:
                while link.ser.in_waiting > 0:
                    raw = link.ser.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            data = json.loads(line)
                            if "dev" in data:
                                packets.append(data)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                self._disconnect_link(link, str(e))
        return packets

    def get_health_summary(self) -> str:
        if self.dry_run:
            return "[SIMULATED / DRY-RUN]"
        tokens = []
        now = time.monotonic()
        for port, link in self.links.items():
            if link.is_online:
                tokens.append(f"{port}:D{link.device_id}")
            else:
                retry_in = max(0.0, self.cooldown - (now - link.last_reconnect_attempt))
                tokens.append(f"{port}:OFF({retry_in:.0f}s)")
        return " ".join(tokens)

    def close_all(self) -> None:
        for port, link in list(self.links.items()):
            if link.is_online:
                old_dev = link.device_id
                if old_dev and self.on_presence_change:
                    try:
                        self.on_presence_change(old_dev, False)
                    except Exception:
                        pass
            if link.ser and link.ser.is_open:
                try:
                    link.ser.close()
                except Exception:
                    pass
                link.ser = None
                link.is_online = False
                link.device_id = None
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
          - Unavailable: Operator shut down / lockout / hardware unplugged -> code 5
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

        # Base and effective health
        w_float = p.get("eff_health", p.get("health", p.get("capacity_factor", 1.0)))
        w_int = int(round(max(0.0, min(1.0, w_float)) * 1000))

        st_code = self._pump_code(p, w_int)
        if any(f.get("type") == "PUMP_TRIP" and f.get("target") == pump_id and f.get("active", True) for f in state.get("faults", [])) and st_code != 5:
            st_code = 4
        lvl, cap = self._get_tank_level_cap(pump_id, state)
        available = 1 if (p.get("available", True) and st_code != 5) else 0

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
    api_url = cfg.get("backend", {}).get("api_url", "http://127.0.0.1:8080").rstrip("/")
    reconnect_delay = cfg.get("backend", {}).get("reconnect_interval_s", 2.0)

    # Queue for presence / status updates to backend
    status_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_presence_change(dev_id: int, online: bool):
        pump_id = PUMPS.get(dev_id, f"P-20{dev_id}")
        logger.info(f"[PRESENCE] Device {dev_id} ({pump_id}) -> {'ONLINE' if online else 'OFFLINE'}")
        status_queue.put_nowait({
            "dev": dev_id,
            "pump": pump_id,
            "online": online
        })

    bus = FaultTolerantSerialBus(cfg, dry_run=dry_run, on_presence_change=on_presence_change)
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
    last_packets: Dict[int, dict] = {}

    if cfg.get("demo_ui", {}).get("enabled", True):
        from demo_ui import start_demo_server
        start_demo_server(cfg.get("demo_ui", {}).get("port", 8090), api_url, bus, current_state, last_packets)

    async def post_hardware_status(client: Any, payload: dict) -> bool:
        """Sends hardware state/sensor packet to FastAPI backend."""
        try:
            if HAS_HTTPX and hasattr(client, "post"):
                resp = await client.post(f"{api_url}/api/hardware/status", json=payload, timeout=2.0)
                return resp.status_code == 200
            else:
                # Fallback to urllib in thread
                import urllib.request
                req = urllib.request.Request(
                    f"{api_url}/api/hardware/status",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                await asyncio.to_thread(urllib.request.urlopen, req, timeout=2.0)
                return True
        except Exception as e:
            logger.debug(f"Failed to post hardware status ({payload.get('pump')}): {e}")
            return False

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
                last_packets[1] = p1
                bus.broadcast_packet(p1)
            if 2 in active_devs:
                p2 = extractor.extract_pump(2, "P-203", current_state)
                last_packets[2] = p2
                bus.broadcast_packet(p2)
            if 3 in active_devs:
                p3 = extractor.extract_pump(3, "P-204", current_state)
                last_packets[3] = p3
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

    async def rx_upstream_task():
        """Reads upstream telemetry from microcontrollers and forwards to backend."""
        logger.info("Upstream serial telemetry reader started.")
        client = httpx.AsyncClient() if HAS_HTTPX else None
        last_sent_telemetry: Dict[int, dict] = {}
        last_sent_time: Dict[int, float] = {}

        try:
            while not stop_event.is_set():
                now = time.monotonic()

                # 1. Drain presence queue (connect/disconnect events)
                while not status_queue.empty():
                    evt = status_queue.get_nowait()
                    await post_hardware_status(client, evt)

                # 2. Read incoming sensor packets from physical microcontrollers
                packets = bus.read_upstream_telemetry()
                for pkt in packets:
                    dev = pkt.get("dev")
                    if dev not in PUMPS:
                        continue
                    pump = pkt.get("pump") or PUMPS[dev]
                    knob_raw = pkt.get("knob")
                    knob_factor = round(knob_raw / 1000.0, 3) if knob_raw is not None else None
                    temp_c = pkt.get("temp")
                    light = pkt.get("light")

                    last_pkt = last_sent_telemetry.get(dev, {})
                    last_tx = last_sent_time.get(dev, 0.0)

                    # Send if significant delta (>1.5% knob or >0.5C temp) or heartbeat >= 1.0s
                    knob_delta = abs((knob_factor or 0) - (last_pkt.get("knob") or 0)) if knob_factor is not None else 0
                    temp_delta = abs((temp_c or 0) - (last_pkt.get("temp") or 0)) if temp_c is not None else 0
                    significant = (knob_delta >= 0.015) or (temp_delta >= 0.5)
                    due = significant or (now - last_tx >= 1.0)

                    if due:
                        payload = {
                            "dev": dev,
                            "pump": pump,
                            "online": True,
                            "knob": knob_factor,
                            "temperature_c": temp_c,
                            "light_level": light,
                            "telemetry": pkt
                        }
                        await post_hardware_status(client, payload)
                        last_sent_telemetry[dev] = {"knob": knob_factor, "temp": temp_c}
                        last_sent_time[dev] = now

                await asyncio.sleep(0.04)  # 25 Hz check
        finally:
            if client:
                await client.aclose()

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
    up_handle = asyncio.create_task(rx_upstream_task())

    try:
        await asyncio.gather(tx_handle, rx_handle, up_handle)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        stop_event.set()
        tx_handle.cancel()
        rx_handle.cancel()
        up_handle.cancel()
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
