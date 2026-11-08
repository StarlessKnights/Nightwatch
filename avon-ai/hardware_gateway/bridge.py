#!/usr/bin/env python3
"""
AVON AI - Computer Hardware Gateway Bridge (3-Node NIGHTWATCH / Multi-Pump HIL)
Connects to the AVON AI simulation backend via WebSocket (/ws/sim)
and streams real-time telemetry to physical Arduino UNO R4s.
- Node 1: Tank (HALL-A / T-104 / T-101)
- Node 2: Duty Pump (CHP-1 / P-203 / P-201)
- Node 3: Output Stream & Security Killswitch (TRT-1 / Pipelines)

Also ingests upstream hardware telemetry (Modulino knob wear/throttle control,
airgap killswitch, pump trip/reset, casing thermal sensors, light sensors)
and relays physical connect/disconnect state to the backend.
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
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    class _MissingListPorts:
        @staticmethod
        def comports() -> list:
            return []

    class _MissingSerialTools:
        list_ports = _MissingListPorts()

    class _MissingSerial:
        tools = _MissingSerialTools()

        class Serial:  # pragma: no cover - only used when dependency is absent
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("pyserial is required for hardware serial access")

    serial = _MissingSerial()
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
    profile: Optional[str] = None


PUMPS = {1: "P-201", 2: "P-203", 3: "P-204"}

PROFILES = (
    "tank", "pump", "output",
    "cooling", "triage", "airgap", "pipeline", "treatment"
)

HELLO = re.compile(
    r"^AVON\|HELLO\|v=(?:1|2)"
    r"(?=.*[|]dev=(?P<dev>[1-3])(?:[|]|$))"
    r"(?=.*[|]profile=(?P<profile>tank|pump|output|cooling|triage|airgap|pipeline|treatment)(?:[|]|$))"
)


def parse_hello(line: str, include_profile: bool = False) -> Any:
    """Parses an AVON handshake greeting banner (v=1 or v=2).
    
    Accepts dev (1, 2, 3) and profile (tank, pump, output, or legacy cooling, triage,
    airgap, pipeline, treatment).
    """
    match = HELLO.match(line.strip())
    if not match:
        return None
    dev = int(match.group("dev"))
    if include_profile:
        return dev, match.group("profile")
    return dev


def parse_hello_profile(line: str) -> Optional[str]:
    """Extracts the profile name from an AVON handshake greeting banner."""
    match = HELLO.match(line.strip())
    return match.group("profile") if match else None


def parse_hello_info(line: str) -> Optional[dict]:
    """Extracts device ID and profile dictionary from handshake banner."""
    match = HELLO.match(line.strip())
    if not match:
        return None
    return {
        "dev": int(match.group("dev")),
        "profile": match.group("profile"),
    }


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
        link.profile = None
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
            profile = None

            # First, check if the MCU already emitted HELLO banner on startup
            try:
                line = ser.readline().decode("utf-8", errors="replace")
                device_id = parse_hello(line)
                profile = parse_hello_profile(line)
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
                    profile = parse_hello_profile(line)
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
            link.profile = profile
            link.is_online = True
            logger.info(f"[ONLINE] Device {device_id} ({profile or PUMPS.get(device_id, 'Node')}) on {link.port}.")

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
        if not any(link.is_online and link.ser for link in self.links.values()):
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
                link.profile = None
        logger.info("All Arduino serial links closed.")


class PumpStateExtractor:
    """Extracts unified telemetry packets for Arduino matrix firmware (v1 and v2)."""

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or {}
        self.seq = 0
        self.local_airgap: int = 0

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) % 65536
        return self.seq

    # ------------------ v2 Extractor Methods (NIGHTWATCH) ------------------

    def extract_tank(self, dev_id: int = 1, state: Optional[dict] = None) -> dict:
        """Extracts telemetry packet for Node 1 (Tank) in v2 format.
        
        Extracts lvl and cap from current_state["tanks"]["HALL-A"] (or fallback "T-104" / "T-101"),
        and alarm flag.
        Format: {"v":2,"seq":N,"dev":1,"lvl":int,"cap":int,"alarm":int}
        """
        if state is None:
            state = {}
        tanks = state.get("tanks", {})
        tank_data = tanks.get("HALL-A") or tanks.get("T-104") or tanks.get("T-101") or {}

        lvl_raw = tank_data.get("volume", tank_data.get("lvl", tank_data.get("level", 600)))
        cap_raw = tank_data.get("capacity", tank_data.get("cap", 1000))
        lvl = max(0, int(round(lvl_raw)))
        cap = max(1, int(round(cap_raw)))

        alarm = self._is_tank_alarm(tank_data, state)

        return {
            "v": 2,
            "seq": self._next_seq(),
            "dev": dev_id,
            "lvl": lvl,
            "cap": cap,
            "alarm": alarm,
        }

    def _is_tank_alarm(self, tank_data: dict, state: dict) -> int:
        if tank_data.get("alarm") is not None:
            return 1 if tank_data["alarm"] else 0
        if state.get("alarm") is not None:
            return 1 if state["alarm"] else 0
        for a in state.get("alarms", []):
            if isinstance(a, dict):
                tag = str(a.get("tag", "")).upper()
                st = str(a.get("state", "")).upper()
                if st != "CLEARED" and (tag in ("HALL-A", "T-104", "T-101", "TANK") or "TANK" in tag):
                    return 1
            elif hasattr(a, "tag"):
                tag = str(getattr(a, "tag", "")).upper()
                st = str(getattr(a, "state", "")).upper()
                if st != "CLEARED" and (tag in ("HALL-A", "T-104", "T-101", "TANK") or "TANK" in tag):
                    return 1
        cap = tank_data.get("capacity", 1000)
        vol = tank_data.get("volume")
        if vol is not None and cap > 0:
            if vol >= 0.95 * cap or vol <= 0.05 * cap:
                return 1
        return 0

    def extract_duty_pump(self, dev_id: int = 2, state: Optional[dict] = None) -> dict:
        """Extracts telemetry packet for Node 2 (Pump) in v2 format.
        
        Duty pump CHP-1 (or fallback P-203 / P-201): state (0=stopped, 1=running, 3=degraded, 4=tripped),
        w (0..1000), flow (float).
        Format: {"v":2,"seq":N,"dev":2,"state":int,"w":int,"flow":float}
        """
        if state is None:
            state = {}
        pumps = state.get("pumps", {})
        pump_id = "CHP-1" if "CHP-1" in pumps else ("P-203" if "P-203" in pumps else "P-201")
        p = pumps.get(pump_id, {})

        w_float = p.get("eff_health", p.get("health", p.get("capacity_factor", p.get("w", 1.0))))
        if isinstance(w_float, (int, float)) and w_float > 1.0:
            w_int = int(round(w_float))
        else:
            w_int = int(round(max(0.0, min(1.0, float(w_float))) * 1000))
        w_int = max(0, min(1000, w_int))

        st_code = self._duty_pump_code(p, w_int, pump_id, state)
        flow = float(round(float(p.get("flow", p.get("Q", 0.0))), 2))

        return {
            "v": 2,
            "seq": self._next_seq(),
            "dev": dev_id,
            "state": st_code,
            "w": w_int,
            "flow": flow,
        }

    def _duty_pump_code(self, p_data: dict, w_int: int, pump_id: str, state: dict) -> int:
        faults_list = state.get("faults", [])
        has_trip = any(
            (f.get("type") == "PUMP_TRIP" and f.get("target") in (pump_id, "CHP-1", "P-203", "P-201") and f.get("active", True))
            for f in faults_list if isinstance(f, dict)
        )
        if has_trip:
            return 4

        if "state" in p_data and isinstance(p_data["state"], int):
            return p_data["state"]

        run_st = str(p_data.get("run_state", "STOPPED")).upper()
        if run_st == "TRIPPED":
            return 4
        if not p_data.get("available", True):
            return 4 if run_st == "RUNNING" else 0

        if run_st == "STOPPED":
            return 0

        if run_st in ("RUNNING", "STARTING"):
            if w_int < 500:
                return 3
            return 1

        if run_st == "DEGRADED":
            return 3

        return 0

    def extract_output(self, dev_id: int = 3, state: Optional[dict] = None) -> dict:
        """Extracts telemetry packet for Node 3 (Output Stream & Security) in v2 format.
        
        Total loop/treatment discharge flow (flow and max_flow from pipelines or treatment),
        airgap flag (0 or 1 from cyber incident state or local toggle), alarm flag.
        Format: {"v":2,"seq":N,"dev":3,"flow":float,"max_flow":float,"airgap":int,"alarm":int}
        """
        if state is None:
            state = {}

        flow = 0.0
        max_flow = 0.0

        if "output" in state and isinstance(state["output"], dict):
            out = state["output"]
            flow = float(out.get("flow", 0.0))
            max_flow = float(out.get("max_flow", out.get("cap", 400.0)))
        elif "treatment" in state and state["treatment"]:
            trt = state["treatment"]
            flow = sum(float(item.get("flow", 0.0)) for item in trt.values() if isinstance(item, dict))
            max_flow = sum(float(item.get("max_intake", item.get("max_flow", item.get("cap", 400.0)))) for item in trt.values() if isinstance(item, dict))
        elif "pipelines" in state and state["pipelines"]:
            pipes = state["pipelines"]
            flow = sum(float(item.get("flow", 0.0)) for item in pipes.values() if isinstance(item, dict))
            max_flow = sum(float(item.get("max_flow", item.get("cap", 400.0))) for item in pipes.values() if isinstance(item, dict))
        else:
            flow = float(state.get("flow", 0.0))
            max_flow = float(state.get("max_flow", 400.0))

        if max_flow <= 0.0:
            max_flow = 400.0

        flow = float(round(flow, 2))
        max_flow = float(round(max_flow, 2))

        airgap = self._is_airgap_engaged(state)
        alarm = self._is_output_alarm(state, flow, max_flow, airgap)

        return {
            "v": 2,
            "seq": self._next_seq(),
            "dev": dev_id,
            "flow": flow,
            "max_flow": max_flow,
            "airgap": airgap,
            "alarm": alarm,
        }

    def _is_airgap_engaged(self, state: dict) -> int:
        if self.local_airgap:
            return 1
        if state.get("airgap") or state.get("airgap_engaged"):
            return 1
        incident = state.get("incident") or state.get("cyber_incident") or {}
        if isinstance(incident, dict):
            if incident.get("airgap") or incident.get("airgap_engaged") or incident.get("engaged"):
                return 1
        return 0

    def _is_output_alarm(self, state: dict, flow: float, max_flow: float, airgap: int) -> int:
        if airgap == 1:
            return 1
        if state.get("alarm") is not None:
            return 1 if state["alarm"] else 0
        if "output" in state and isinstance(state["output"], dict) and state["output"].get("alarm") is not None:
            return 1 if state["output"]["alarm"] else 0
        if max_flow > 0 and flow >= max_flow:
            return 1
        for a in state.get("alarms", []):
            if isinstance(a, dict):
                tag = str(a.get("tag", "")).upper()
                cond = str(a.get("condition", "")).upper()
                st = str(a.get("state", "")).upper()
                if st != "CLEARED" and (any(k in tag for k in ("TRT", "PIPE", "OUTPUT", "SECURITY", "CYBER")) or "CAP" in cond):
                    return 1
            elif hasattr(a, "tag"):
                tag = str(getattr(a, "tag", "")).upper()
                st = str(getattr(a, "state", "")).upper()
                if st != "CLEARED" and any(k in tag for k in ("TRT", "PIPE", "OUTPUT", "SECURITY", "CYBER")):
                    return 1
        return 0

    def extract_node(self, dev_id: int, state: dict) -> dict:
        """Extracts telemetry packet for a node based on dev_id (1=tank, 2=pump, 3=output)."""
        if dev_id == 1:
            return self.extract_tank(dev_id, state)
        elif dev_id == 2:
            return self.extract_duty_pump(dev_id, state)
        elif dev_id == 3:
            return self.extract_output(dev_id, state)
        else:
            return self.extract_pump(dev_id, f"P-20{dev_id}", state)

    # ------------------ Legacy v1 Extractor Methods ------------------

    def _pump_code(self, p_data: dict, w_int: int) -> int:
        """
        Pump state codes:
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
        """Extracts telemetry packet for an outflow pump (P-201, P-203, P-204) in v1 format."""
        pumps = state.get("pumps", {})
        p = pumps.get(pump_id, {})

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


async def post_hardware_status(client: Any, payload: dict, api_url: str = "http://127.0.0.1:8000") -> bool:
    """Sends hardware state/sensor packet to FastAPI backend."""
    try:
        if HAS_HTTPX and hasattr(client, "post"):
            resp = await client.post(f"{api_url}/api/hardware/status", json=payload, timeout=2.0)
            return resp.status_code == 200
        else:
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


async def post_incident_airgap(client: Any, payload: dict, api_url: str = "http://127.0.0.1:8000") -> bool:
    """Sends airgap killswitch event to backend incident API."""
    try:
        if HAS_HTTPX and hasattr(client, "post"):
            resp = await client.post(f"{api_url}/api/incident/airgap", json=payload, timeout=2.0)
            return resp.status_code == 200
        else:
            import urllib.request
            req = urllib.request.Request(
                f"{api_url}/api/incident/airgap",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=2.0)
            return True
    except Exception as e:
        logger.debug(f"Failed to post incident airgap: {e}")
        return False


async def trigger_pump_trip(
    client: Any,
    pump_id: str,
    action: Optional[str] = None,
    current_state: Optional[dict] = None,
    api_url: str = "http://127.0.0.1:8000"
) -> bool:
    """Injects or resets a PUMP_TRIP fault via the FastAPI backend."""
    try:
        state = current_state if current_state is not None else {}
        faults_list = state.get("faults", [])
        existing_trip = next((f for f in faults_list if f.get("type") == "PUMP_TRIP" and f.get("target") == pump_id and f.get("active", True)), None)

        if action in ("clear", "reset", "TRIP_RESET") or (action is None and existing_trip is not None):
            if existing_trip:
                fid = existing_trip.get("id")
                if fid:
                    logger.info(f"[BUTTON RESET] Clearing trip error on {pump_id} (fault {fid})")
                    if HAS_HTTPX and hasattr(client, "delete"):
                        await client.delete(f"{api_url}/api/faults/{fid}", timeout=2.0)
                    else:
                        import urllib.request
                        req = urllib.request.Request(f"{api_url}/api/faults/{fid}", method="DELETE")
                        await asyncio.to_thread(urllib.request.urlopen, req, timeout=2.0)
                    state["faults"] = [f for f in faults_list if f.get("id") != fid]
                    if "pumps" in state and pump_id in state["pumps"]:
                        if state["pumps"][pump_id].get("run_state") == "TRIPPED":
                            state["pumps"][pump_id]["run_state"] = "RUNNING"
                    return True
            else:
                logger.info(f"[BUTTON RESET] No active trip on {pump_id} to clear.")
                return True

        if action in ("trip", "inject", "PUMP_TRIP") or (action is None and existing_trip is None):
            logger.info(f"[BUTTON TRIP] Tripping {pump_id} via physical Modulino Button!")
            payload = {"type": "PUMP_TRIP", "target": pump_id, "params": {"reason": "Modulino hardware button trip"}}
            resp_id = f"trip-{pump_id}-{int(time.time())}"
            if HAS_HTTPX and hasattr(client, "post"):
                resp = await client.post(f"{api_url}/api/faults", json=payload, timeout=2.0)
                if resp.status_code == 200:
                    try:
                        resp_id = resp.json().get("id", resp_id)
                    except Exception:
                        pass
            else:
                import urllib.request
                req = urllib.request.Request(
                    f"{api_url}/api/faults",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                await asyncio.to_thread(urllib.request.urlopen, req, timeout=2.0)
            if "faults" not in state:
                state["faults"] = []
            state["faults"].append({
                "id": resp_id,
                "type": "PUMP_TRIP",
                "target": pump_id,
                "active": True
            })
            if "pumps" in state and pump_id in state["pumps"]:
                state["pumps"][pump_id]["run_state"] = "TRIPPED"
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to trigger pump trip for {pump_id}: {e}")
        return False


async def handle_upstream_packet(
    pkt: dict,
    current_state: dict,
    client: Any = None,
    api_url: str = "http://127.0.0.1:8000",
    extractor: Optional[PumpStateExtractor] = None,
) -> bool:
    """Dispatches upstream packets from physical microcontrollers according to event type."""
    dev = pkt.get("dev")
    evt_name = str(pkt.get("event") or pkt.get("evt") or pkt.get("type") or pkt.get("cmd") or pkt.get("action") or "").upper()

    # 1. AIRGAP_KILLSWITCH (typically from Node 3)
    is_airgap = (
        "AIRGAP_KILLSWITCH" in evt_name or
        "AIRGAP" in evt_name or
        bool(pkt.get("airgap_killswitch")) or
        "AIRGAP_KILLSWITCH" in pkt or
        (dev == 3 and str(pkt.get("btn", "")).upper() == "A")
    )
    if is_airgap:
        if extractor is not None:
            extractor.local_airgap = 1 if extractor.local_airgap == 0 else 0
            current_state["airgap"] = extractor.local_airgap
        else:
            current_state["airgap"] = 1 if not current_state.get("airgap", 0) else 0

        logger.info(f"[AIRGAP KILLSWITCH] Local airgap toggled -> {current_state.get('airgap')}")
        payload = {"engaged": True, "source": "hardware_button_a"}
        await post_incident_airgap(client, payload, api_url=api_url)
        return True

    # 2. PUMP_TRIP / TRIP_RESET (typically from Node 3 or any node)
    is_trip = "PUMP_TRIP" in evt_name or "PUMP_TRIP" in pkt or (dev == 3 and str(pkt.get("btn", "")).upper() == "B")
    is_reset = "TRIP_RESET" in evt_name or "TRIP_RESET" in pkt or "RESET" in evt_name or (dev == 3 and str(pkt.get("btn", "")).upper() == "C")
    if is_trip or is_reset:
        pumps_in_state = current_state.get("pumps", {})
        trip_pump = pkt.get("target_pump") or pkt.get("pump") or pkt.get("trip_pump")
        if not trip_pump:
            if "CHP-1" in pumps_in_state:
                trip_pump = "CHP-1"
            elif "P-203" in pumps_in_state:
                trip_pump = "P-203"
            elif "P-201" in pumps_in_state:
                trip_pump = "P-201"
            else:
                trip_pump = "CHP-1"

        action = "reset" if is_reset else "trip"
        logger.info(f"[PUMP EVENT] {action.upper()} triggered for {trip_pump}")
        await trigger_pump_trip(client, trip_pump, action=action, current_state=current_state, api_url=api_url)
        return True

    # Legacy trip by device button
    trip_dev = pkt.get("trip_dev")
    trip_pump = pkt.get("trip_pump") or (PUMPS.get(trip_dev) if trip_dev in PUMPS else None)
    if trip_pump:
        logger.info(f"[BUTTON EVENT] Modulino button triggered for {trip_pump} (Device {trip_dev})")
        await trigger_pump_trip(client, trip_pump, current_state=current_state, api_url=api_url)
        return True

    # 3. Modulino Knob wear/throttle adjustment (typically Node 2)
    knob_raw = None
    if "knob" in pkt:
        knob_raw = pkt["knob"]
    elif "KNOB" in pkt:
        knob_raw = pkt["KNOB"]
    elif "KNOB" in evt_name:
        knob_raw = pkt.get("val", pkt.get("value", pkt.get("knob", pkt.get("factor", 1000))))

    if knob_raw is not None:
        try:
            k_val = float(knob_raw)
            if k_val > 1.0:
                knob_factor = round(k_val / 1000.0, 3)
            else:
                knob_factor = round(k_val, 3)
            knob_factor = max(0.0, min(1.0, knob_factor))
        except (ValueError, TypeError):
            knob_factor = None

        if knob_factor is not None:
            dev_id = dev if dev is not None else 2
            target_dev = pkt.get("target_dev", dev_id)
            target_pump = pkt.get("target_pump") or pkt.get("pump")
            if not target_pump:
                pumps_in_state = current_state.get("pumps", {})
                if "CHP-1" in pumps_in_state:
                    target_pump = "CHP-1"
                elif "P-203" in pumps_in_state:
                    target_pump = "P-203"
                elif "P-201" in pumps_in_state:
                    target_pump = "P-201"
                else:
                    target_pump = "CHP-1"

            payload_knob = {
                "dev": target_dev,
                "pump": target_pump,
                "online": True,
                "knob": knob_factor,
                "telemetry": pkt
            }
            await post_hardware_status(client, payload_knob, api_url=api_url)
            if "pumps" in current_state and target_pump in current_state["pumps"]:
                current_state["pumps"][target_pump]["knob_factor"] = knob_factor
                current_state["pumps"][target_pump]["eff_health"] = knob_factor
                current_state["pumps"][target_pump]["health"] = knob_factor
            return True

    # 4. Thermal & Optical sensor telemetry
    temp_c = pkt.get("temp")
    light = pkt.get("light")
    if temp_c is not None or light is not None:
        dev_id = dev if dev is not None else 2
        pump = pkt.get("pump") or PUMPS.get(dev_id, "CHP-1")
        payload_local = {
            "dev": dev_id,
            "pump": pump,
            "online": True,
            "temperature_c": temp_c,
            "light_level": light,
            "telemetry": pkt
        }
        await post_hardware_status(client, payload_local, api_url=api_url)
        return True

    return False


async def run_gateway(config_path: str, dry_run: bool = False, verbose: bool = False) -> None:
    if verbose:
        logger.setLevel(logging.DEBUG)

    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ws_url = cfg.get("backend", {}).get("ws_url", "ws://127.0.0.1:8000/ws/sim")
    api_url = cfg.get("backend", {}).get("api_url", "http://127.0.0.1:8000").rstrip("/")
    reconnect_delay = cfg.get("backend", {}).get("reconnect_interval_s", 2.0)

    # Queue for presence / status updates to backend
    status_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_presence_change(dev_id: int, online: bool):
        pump_id = "CHP-1" if (dev_id == 2 and "CHP-1" in current_state.get("pumps", {})) else PUMPS.get(dev_id, f"P-20{dev_id}")
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
            "CHP-1": {"run_state": "RUNNING", "health": 1.0, "flow": 180.0, "available": True},
            "P-201": {"run_state": "RUNNING", "health": 1.0, "flow": 150.0, "available": True},
            "P-203": {"run_state": "RUNNING", "health": 1.0, "flow": 180.0, "available": True},
            "P-204": {"run_state": "STOPPED", "health": 1.0, "flow": 0.0, "available": True}
        },
        "tanks": {
            "HALL-A": {"volume": 750, "capacity": 1000},
            "T-101": {"volume": 600, "capacity": 1000},
            "T-104": {"volume": 880, "capacity": 1000}
        },
        "treatment": {
            "TRT-1": {"flow": 330.0, "max_intake": 400.0}
        },
        "pipelines": {
            "PL-MAIN": {"flow": 330.0, "max_flow": 400.0}
        },
        "airgap": 0,
        "faults": [],
        "alarms": [],
        "t_min": 0
    }

    stop_event = asyncio.Event()
    last_packets: Dict[int, dict] = {}

    if cfg.get("demo_ui", {}).get("enabled", True):
        from demo_ui import start_demo_server
        start_demo_server(cfg.get("demo_ui", {}).get("port", 8090), api_url, bus, current_state, last_packets)

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

            proto_version = cfg.get("protocol_version", 2)
            if proto_version == 2:
                # Node 1: Tank (HALL-A / T-104 / T-101)
                if 1 in active_devs:
                    p1 = extractor.extract_tank(1, current_state)
                    last_packets[1] = p1
                    bus.broadcast_packet(p1)
                # Node 2: Duty Pump (CHP-1 / P-203 / P-201)
                if 2 in active_devs:
                    p2 = extractor.extract_duty_pump(2, current_state)
                    last_packets[2] = p2
                    bus.broadcast_packet(p2)
                # Node 3: Output Stream & Security Killswitch
                if 3 in active_devs:
                    p3 = extractor.extract_output(3, current_state)
                    last_packets[3] = p3
                    bus.broadcast_packet(p3)
            else:
                # Legacy v1
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
                chp1 = pumps.get("CHP-1", pumps.get("P-203", {}))
                tanks = current_state.get("tanks", {})
                tank_a = tanks.get("HALL-A", tanks.get("T-104", {}))
                lvl_val = tank_a.get("volume", 0)
                logger.info(
                    f"Tick t={current_state.get('t_min', 0)}m | "
                    f"Tank(D1): {lvl_val:.0f} bbl | "
                    f"Pump(D2): {chp1.get('flow', 0):.0f} bbl/hr ({chp1.get('run_state', 'STOPPED')}) | "
                    f"Output(D3): airgap={extractor.local_airgap} | "
                    f"Links: [{health}]"
                )
                last_log = now

            # Stream at 10 Hz (100 ms interval)
            await asyncio.sleep(0.1)

    async def rx_upstream_task():
        """Reads upstream telemetry from microcontrollers and forwards to backend."""
        logger.info("Upstream serial telemetry reader started.")
        client = httpx.AsyncClient() if HAS_HTTPX else None

        try:
            while not stop_event.is_set():
                # 1. Drain presence queue (connect/disconnect events)
                while not status_queue.empty():
                    evt = status_queue.get_nowait()
                    await post_hardware_status(client, evt, api_url=api_url)

                # 2. Read incoming sensor packets from physical microcontrollers
                packets = bus.read_upstream_telemetry()
                for pkt in packets:
                    await handle_upstream_packet(
                        pkt,
                        current_state,
                        client=client,
                        api_url=api_url,
                        extractor=extractor,
                    )

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
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate serial writes without hardware Arduinos")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    try:
        asyncio.run(run_gateway(args.config, dry_run=args.dry_run, verbose=args.verbose))
    except KeyboardInterrupt:
        logger.info("Gateway stopped by operator.")


if __name__ == "__main__":
    main()
