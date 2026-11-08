import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import (
    FaultTolerantSerialBus,
    HAS_SERIAL,
    PumpStateExtractor,
    parse_hello,
    parse_hello_profile,
    parse_hello_info,
    handle_upstream_packet,
)
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
        # Every connected link receives the packet. Each firmware instance
        # accepts only the packet matching its compiled DEVICE_ID.
        self.assertEqual([len(fake[p].writes) for p in devices], [1, 1, 1])

    def test_missing_pyserial_does_not_silently_enable_dry_run(self):
        cfg = {"serial": {"active_devices": [1, 2, 3], "auto_detect": False}}
        with patch("bridge.HAS_SERIAL", False):
            bus = FaultTolerantSerialBus(cfg)
            with self.assertRaisesRegex(RuntimeError, "pyserial is required"):
                bus.connect_all()

        with patch("bridge.HAS_SERIAL", False):
            bus = FaultTolerantSerialBus(cfg, dry_run=True)
            bus.connect_all()
            self.assertTrue(bus.dry_run)

    def test_hello_v2_and_profiles(self):
        # v2 banners for 3 physical nodes
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=1|profile=tank|fw=2.0.0|caps=matrix"), 1)
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=2|profile=pump|fw=2.0.0|caps=matrix,knob"), 2)
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=3|profile=output|fw=2.0.0|caps=matrix,buttons"), 3)

        # parse_hello with include_profile
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=1|profile=tank|fw=2.0.0", include_profile=True), (1, "tank"))
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=2|profile=pump|fw=2.0.0", include_profile=True), (2, "pump"))
        self.assertEqual(parse_hello("AVON|HELLO|v=2|dev=3|profile=output|fw=2.0.0", include_profile=True), (3, "output"))

        # parse_hello_profile
        self.assertEqual(parse_hello_profile("AVON|HELLO|v=2|dev=3|profile=output|fw=2.0.0"), "output")
        self.assertEqual(parse_hello_profile("AVON|HELLO|v=1|dev=1|profile=cooling|fw=1.0.0"), "cooling")

        # parse_hello_info
        info = parse_hello_info("AVON|HELLO|v=2|dev=2|profile=pump|fw=2.0.0")
        self.assertIsNotNone(info)
        self.assertEqual(info["dev"], 2)
        self.assertEqual(info["profile"], "pump")

        # Invalid cases
        self.assertIsNone(parse_hello("AVON|HELLO|v=3|dev=1|profile=tank"))
        self.assertIsNone(parse_hello("AVON|HELLO|v=2|dev=4|profile=tank"))
        self.assertIsNone(parse_hello("AVON|HELLO|v=2|dev=1|profile=unknown"))
        self.assertIsNone(parse_hello("MALFORMED_LINE"))

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

    def test_upstream_single_knob_target_switching(self):
        cfg = {"serial": {"active_devices": [1, 2, 3], "auto_detect": False}}
        with patch("bridge.serial.tools.list_ports.comports", return_value=[]):
            bus = FaultTolerantSerialBus(cfg)

        from bridge import SerialPortLink
        link = SerialPortLink(port="COM4", is_online=True, device_id=1)
        fake = FakeSerial()
        fake.rx_buffer.append(b'{"v":1,"dev":1,"pump":"P-201","online":1,"target_dev":2,"target_pump":"P-203","knob":450,"temp":24.5}\n')
        link.ser = fake
        bus.links["COM4"] = link

        packets = bus.read_upstream_telemetry()
        self.assertEqual(len(packets), 1)
        pkt = packets[0]
        self.assertEqual(pkt["dev"], 1)
        self.assertEqual(pkt["pump"], "P-201")
        self.assertEqual(pkt["target_dev"], 2)
        self.assertEqual(pkt["target_pump"], "P-203")
        self.assertEqual(pkt["knob"], 450)

    def test_extract_tank_v2(self):
        extractor = PumpStateExtractor({})
        state = {
            "tanks": {
                "HALL-A": {"volume": 725.5, "capacity": 1000},
                "T-104": {"volume": 850, "capacity": 1000}
            },
            "alarms": []
        }
        pkt = extractor.extract_tank(1, state)
        self.assertEqual(pkt["v"], 2)
        self.assertEqual(pkt["dev"], 1)
        self.assertEqual(pkt["lvl"], 726)
        self.assertEqual(pkt["cap"], 1000)
        self.assertEqual(pkt["alarm"], 0)

        # Alarm active in state
        state["alarms"] = [{"tag": "HALL-A", "state": "ACTIVE_UNACK"}]
        pkt_alarm = extractor.extract_tank(1, state)
        self.assertEqual(pkt_alarm["alarm"], 1)

        # Fallback to T-104 if HALL-A missing
        state_fallback = {
            "tanks": {"T-104": {"volume": 600, "capacity": 1000}},
            "alarms": []
        }
        pkt_fallback = extractor.extract_tank(1, state_fallback)
        self.assertEqual(pkt_fallback["lvl"], 600)
        self.assertEqual(pkt_fallback["cap"], 1000)

    def test_extract_duty_pump_v2(self):
        extractor = PumpStateExtractor({})
        # Running duty pump CHP-1 with healthy impeller
        state = {
            "pumps": {
                "CHP-1": {"run_state": "RUNNING", "eff_health": 0.95, "flow": 210.4, "available": True}
            },
            "faults": []
        }
        pkt = extractor.extract_duty_pump(2, state)
        self.assertEqual(pkt["v"], 2)
        self.assertEqual(pkt["dev"], 2)
        self.assertEqual(pkt["state"], 1)  # RUNNING
        self.assertEqual(pkt["w"], 950)
        self.assertEqual(pkt["flow"], 210.4)

        # Degraded pump (w < 500)
        state["pumps"]["CHP-1"]["eff_health"] = 0.42
        pkt_degraded = extractor.extract_duty_pump(2, state)
        self.assertEqual(pkt_degraded["state"], 3)  # DEGRADED
        self.assertEqual(pkt_degraded["w"], 420)

        # Tripped pump
        state["faults"] = [{"type": "PUMP_TRIP", "target": "CHP-1", "active": True}]
        pkt_tripped = extractor.extract_duty_pump(2, state)
        self.assertEqual(pkt_tripped["state"], 4)  # TRIPPED

        # Stopped pump
        state["faults"] = []
        state["pumps"]["CHP-1"]["run_state"] = "STOPPED"
        pkt_stopped = extractor.extract_duty_pump(2, state)
        self.assertEqual(pkt_stopped["state"], 0)  # STOPPED

    def test_extract_output_v2(self):
        extractor = PumpStateExtractor({})
        state = {
            "treatment": {
                "TRT-1": {"flow": 315.6, "max_intake": 400.0}
            },
            "pipelines": {},
            "airgap": 0,
            "alarms": []
        }
        pkt = extractor.extract_output(3, state)
        self.assertEqual(pkt["v"], 2)
        self.assertEqual(pkt["dev"], 3)
        self.assertEqual(pkt["flow"], 315.6)
        self.assertEqual(pkt["max_flow"], 400.0)
        self.assertEqual(pkt["airgap"], 0)
        self.assertEqual(pkt["alarm"], 0)

        # Airgap isolation engaged via incident
        state["incident"] = {"airgap": True}
        pkt_airgap = extractor.extract_output(3, state)
        self.assertEqual(pkt_airgap["airgap"], 1)

        # Local airgap override
        extractor.local_airgap = 1
        state["incident"] = {}
        pkt_local_airgap = extractor.extract_output(3, state)
        self.assertEqual(pkt_local_airgap["airgap"], 1)

    def test_handle_upstream_airgap_killswitch(self):
        extractor = PumpStateExtractor({})
        current_state = {"airgap": 0, "pumps": {"CHP-1": {"run_state": "RUNNING"}}}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200))

        # Modulino Button A emits AIRGAP_KILLSWITCH
        pkt = {"dev": 3, "evt": "AIRGAP_KILLSWITCH", "btn": "A"}
        loop = asyncio.new_event_loop()
        handled = loop.run_until_complete(
            handle_upstream_packet(pkt, current_state, client=mock_client, api_url="http://127.0.0.1:8000", extractor=extractor)
        )
        loop.close()

        self.assertTrue(handled)
        self.assertEqual(extractor.local_airgap, 1)
        self.assertEqual(current_state["airgap"], 1)
        mock_client.post.assert_called_with(
            "http://127.0.0.1:8000/api/incident/airgap",
            json={"engaged": True, "source": "hardware_button_a"},
            timeout=2.0
        )

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

    def test_handle_upstream_modulino_trip_and_reset(self):
        extractor = PumpStateExtractor({})
        current_state = {"pumps": {"CHP-1": {"run_state": "RUNNING"}}, "faults": []}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200, json=lambda: {"id": "fault-1"}))
        mock_client.delete = AsyncMock(return_value=AsyncMock(status_code=200))

        loop = asyncio.new_event_loop()
        # Button B trips pump
        pkt_trip = {"dev": 3, "btn": "B"}
        handled_trip = loop.run_until_complete(
            handle_upstream_packet(pkt_trip, current_state, client=mock_client, api_url="http://127.0.0.1:8000", extractor=extractor)
        )
        self.assertTrue(handled_trip)
        self.assertEqual(current_state["pumps"]["CHP-1"]["run_state"], "TRIPPED")

        # Button C resets pump
        pkt_reset = {"dev": 3, "btn": "C"}
        handled_reset = loop.run_until_complete(
            handle_upstream_packet(pkt_reset, current_state, client=mock_client, api_url="http://127.0.0.1:8000", extractor=extractor)
        )
        self.assertTrue(handled_reset)
        self.assertEqual(current_state["pumps"]["CHP-1"]["run_state"], "RUNNING")
        loop.close()

    def test_handle_upstream_thermal_telemetry(self):
        extractor = PumpStateExtractor({})
        current_state = {"pumps": {"CHP-1": {"run_state": "RUNNING"}}}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200))

        pkt_thermal = {"dev": 2, "pump": "CHP-1", "temp": 42.5, "light": 350.0}
        loop = asyncio.new_event_loop()
        handled = loop.run_until_complete(
            handle_upstream_packet(pkt_thermal, current_state, client=mock_client, api_url="http://127.0.0.1:8000", extractor=extractor)
        )
        loop.close()
        self.assertTrue(handled)
        mock_client.post.assert_called_with(
            "http://127.0.0.1:8000/api/hardware/status",
            json={"dev": 2, "pump": "CHP-1", "online": True, "temperature_c": 42.5, "light_level": 350.0, "telemetry": pkt_thermal},
            timeout=2.0
        )

    def test_handle_upstream_unhandled_packet(self):
        extractor = PumpStateExtractor({})
        current_state = {}
        mock_client = AsyncMock()

        pkt_unknown = {"foo": "bar"}
        loop = asyncio.new_event_loop()
        handled = loop.run_until_complete(
            handle_upstream_packet(pkt_unknown, current_state, client=mock_client, api_url="http://127.0.0.1:8000", extractor=extractor)
        )
        loop.close()
        self.assertFalse(handled)


    def test_datacenter_cooling_sim_outage_to_hardware_packets(self):
        extractor = PumpStateExtractor({})
        state = {
            "pumps": {
                "CHP-1": {"run_state": "RUNNING", "eff_health": 1.0, "available": True},
                "CHP-2": {"run_state": "STOPPED", "eff_health": 1.0, "available": True},
            },
            "tanks": {
                "HALL-A": {"volume": 600, "capacity": 1000}
            },
            "faults": []
        }

        # 1. Normal state: Device 1 & 2 run fluid waves, Device 3 is idle/standby
        p1 = extractor.extract_pump(1, "P-201", state)
        self.assertEqual(p1["v"], 1)
        self.assertEqual(p1["dev"], 1)
        self.assertEqual(p1["pump"], "P-201")
        self.assertEqual(p1["state"], 1)
        self.assertEqual(p1["available"], 1)
        self.assertEqual(p1["lvl"], 600)
        self.assertEqual(p1["cap"], 1000)

        p2 = extractor.extract_pump(2, "P-203", state)
        self.assertEqual(p2["dev"], 2)
        self.assertEqual(p2["pump"], "P-203")
        self.assertEqual(p2["state"], 1)

        p3 = extractor.extract_pump(3, "P-204", state)
        self.assertEqual(p3["dev"], 3)
        self.assertEqual(p3["pump"], "P-204")
        self.assertEqual(p3["state"], 0)

        # 2. Sim outage: Trip on CHP-1 triggers state 4 (caution triangle)
        state["pumps"]["CHP-1"]["run_state"] = "TRIPPED"
        state["faults"] = [{"type": "PUMP_TRIP", "target": "CHP-1", "active": True}]
        p1_tripped = extractor.extract_pump(1, "P-201", state)
        p2_tripped = extractor.extract_pump(2, "P-203", state)
        self.assertEqual(p1_tripped["state"], 4)
        self.assertEqual(p2_tripped["state"], 4)

        # Standby CHP-2 starts on changeover -> Device 3 immediately shows water waves
        state["pumps"]["CHP-2"]["run_state"] = "RUNNING"
        p3_running = extractor.extract_pump(3, "P-204", state)
        self.assertEqual(p3_running["state"], 1)

        # 3. Sim outage: Unavailable on CHP-1 triggers state 5 (solid X)
        state["pumps"]["CHP-1"]["available"] = False
        p1_unavail = extractor.extract_pump(1, "P-201", state)
        self.assertEqual(p1_unavail["state"], 5)
        self.assertEqual(p1_unavail["available"], 0)


if __name__ == "__main__":
    unittest.main()
