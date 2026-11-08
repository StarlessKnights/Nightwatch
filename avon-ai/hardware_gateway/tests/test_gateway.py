import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import FaultTolerantSerialBus, HAS_SERIAL, PumpStateExtractor, parse_hello
from demo_ui import perform_action


class FakeSerial:
    def __init__(self, hello=b""):
        self.hello = hello
        self.writes = []
        self.is_open = True
        self.rx_buffer = []

    def readline(self):
        if self.hello:
            line, self.hello = self.hello, b""
            return line
        if self.rx_buffer:
            return self.rx_buffer.pop(0)
        return b""

    @property
    def in_waiting(self):
        return sum(len(line) for line in self.rx_buffer)

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False


class GatewayTests(unittest.TestCase):
    def test_hello_and_identity_routing(self):
        if not HAS_SERIAL:
            self.skipTest("pyserial is required for serial identity routing tests")
        self.assertEqual(parse_hello("AVON|HELLO|v=1|dev=2|profile=pump|fw=0.2.0-pump"), 2)
        self.assertEqual(
            parse_hello("AVON|HELLO|v=1|dev=1|pump=P-201|profile=pump|fw=0.3.0-hil|caps=matrix,knob,temp,light,buzzer"),
            1
        )
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

    def test_presence_callback_on_connect_and_disconnect(self):
        events = []
        cfg = {"serial": {"active_devices": [1, 2, 3], "auto_detect": False, "macos_ports": {}}}
        with patch("bridge.serial.tools.list_ports.comports", return_value=[]):
            bus = FaultTolerantSerialBus(cfg, on_presence_change=lambda d, on: events.append((d, on)))

        from bridge import SerialPortLink
        link = SerialPortLink(port="COM4")
        bus.links["COM4"] = link
        fake = FakeSerial(b"AVON|HELLO|v=1|dev=1|pump=P-201|profile=pump|fw=0.3.0-hil|caps=matrix\n")
        with patch("bridge.serial.Serial", return_value=fake):
            connected = bus._try_connect(link)

        self.assertTrue(connected)
        self.assertEqual(events, [(1, True)])

        # Trigger disconnect
        bus._disconnect_link(link, "Unplugged")
        self.assertFalse(link.is_online)
        self.assertIsNone(link.device_id)
        self.assertEqual(events, [(1, True), (1, False)])

    def test_upstream_telemetry_reading(self):
        cfg = {"serial": {"active_devices": [1, 2, 3], "auto_detect": False}}
        with patch("bridge.serial.tools.list_ports.comports", return_value=[]):
            bus = FaultTolerantSerialBus(cfg)

        from bridge import SerialPortLink
        link = SerialPortLink(port="COM5", is_online=True, device_id=2)
        fake = FakeSerial()
        fake.rx_buffer.append(b'{"v":1,"dev":2,"pump":"P-203","online":1,"knob":750,"temp":38.2,"light":512}\n')
        link.ser = fake
        bus.links["COM5"] = link

        packets = bus.read_upstream_telemetry()
        self.assertEqual(len(packets), 1)
        pkt = packets[0]
        self.assertEqual(pkt["dev"], 2)
        self.assertEqual(pkt["pump"], "P-203")
        self.assertEqual(pkt["knob"], 750)
        self.assertEqual(pkt["temp"], 38.2)

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

    def test_all_dashboard_pump_states_map_to_firmware_codes(self):
        extractor = PumpStateExtractor({})
        base = {"pumps": {"P-201": {"run_state": "STOPPED", "eff_health": 1.0, "available": True}},
                "tanks": {"T-101": {"volume": 600, "capacity": 1000}}, "faults": []}
        expected = {
            "STOPPED": 0,
            "RUNNING": 1,
            "STARTING": 2,
        }
        for run_state, code in expected.items():
            base["pumps"]["P-201"].update(run_state=run_state, available=True, eff_health=1.0)
            self.assertEqual(extractor.extract_pump(1, "P-201", base)["state"], code)

        base["pumps"]["P-201"].update(run_state="RUNNING", eff_health=0.49)
        self.assertEqual(extractor.extract_pump(1, "P-201", base)["state"], 3)
        base["pumps"]["P-201"].update(run_state="TRIPPED", eff_health=1.0)
        self.assertEqual(extractor.extract_pump(1, "P-201", base)["state"], 4)
        base["pumps"]["P-201"].update(run_state="STOPPED", available=False)
        self.assertEqual(extractor.extract_pump(1, "P-201", base)["state"], 5)

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
