import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import FaultTolerantSerialBus, PumpStateExtractor, parse_hello
from demo_ui import perform_action


class FakeSerial:
    def __init__(self, hello):
        self.hello = hello
        self.writes = []
        self.is_open = True

    def readline(self):
        line, self.hello = self.hello, b""
        return line

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False


class GatewayTests(unittest.TestCase):
    def test_hello_and_identity_routing(self):
        self.assertEqual(parse_hello("AVON|HELLO|v=1|dev=2|profile=pump|fw=0.2.0-pump"), 2)
        self.assertIsNone(parse_hello("AVON|HELLO|v=1|dev=5|profile=PUMP|fw=0.2.0"))
        cfg = {"serial": {"active_devices": [1, 2, 3], "auto_detect": False, "macos_ports": {}}}
        with patch("bridge.serial.tools.list_ports.comports", return_value=[]):
            bus = FaultTolerantSerialBus(cfg)
        from bridge import SerialPortLink
        bus.links = {f"port{n}": SerialPortLink(f"port{n}") for n in (1, 2, 3)}
        devices = {"port1": 3, "port2": 1, "port3": 2}
        fake = {port: FakeSerial(f"AVON|HELLO|v=1|dev={dev}|profile=pump|fw=0.2.0-pump\n".encode()) for port, dev in devices.items()}
        with patch("bridge.serial.Serial", side_effect=lambda port, *a, **kw: fake[port]):
            bus.connect_all()
        bus.broadcast_packet({"v": 1, "dev": 2, "pump": "P-203"})
        self.assertEqual([len(fake[p].writes) for p in devices], [0, 0, 1])

    def test_packet_health_level_and_trip_priority(self):
        extractor = PumpStateExtractor({})
        state = {"pumps": {"P-201": {"run_state": "RUNNING", "eff_health": .499, "available": True}}, "tanks": {"T-101": {"volume": 200, "capacity": 1000}}}
        packet = extractor.extract_pump(1, "P-201", state)
        self.assertEqual((packet["w"], packet["lvl"], packet["cap"]), (499, 200, 1000))
        self.assertEqual(packet["state"], 3)
        state["faults"] = [{"type": "PUMP_TRIP", "target": "P-201", "active": True}]
        self.assertEqual(extractor.extract_pump(1, "P-201", state)["state"], 4)
        state["pumps"]["P-201"]["available"] = False
        self.assertEqual(extractor.extract_pump(1, "P-201", state)["state"], 5)

    def test_ui_actions_target_selected_pump(self):
        state = {"snapshot": {"state": {"faults": [], "pumps": {"P-203": {"available": True}}}}}
        calls = []
        def fake_backend(_, method, path, body=None):
            calls.append((method, path, body))
            return state if path == "/api/network" else {"ok": True}
        with patch("demo_ui.backend", side_effect=fake_backend):
            perform_action("http://backend", {"kind": "trip", "dev": 2})
            perform_action("http://backend", {"kind": "wear", "dev": 2, "value": .45})
            perform_action("http://backend", {"kind": "unavailable", "dev": 2})
            perform_action("http://backend", {"kind": "reset", "dev": 2})
        self.assertIn(("POST", "/api/faults", {"type": "PUMP_TRIP", "target": "P-203", "params": {}}), calls)
        self.assertIn(("PATCH", "/api/assets/P-203", {"health": .45}), calls)
        self.assertIn(("PATCH", "/api/assets/P-203", {"available": False}), calls)
        self.assertIn(("PATCH", "/api/assets/P-203", {"health": 1.0, "available": True}), calls)


if __name__ == "__main__":
    unittest.main()
