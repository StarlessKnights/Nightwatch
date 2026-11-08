"""Tests for hardware presence, physical connectivity coupling, and sensor telemetry."""
import pytest
from starlette.testclient import TestClient

from app.main import app, session
from app.state import RUNNING, STARTING, STOPPED, TRIPPED


@pytest.fixture(autouse=True)
def reset_session():
    session.reset()
    yield
    session.reset()


def test_hardware_connection_enables_and_starts_pump():
    # Initially mock pump is not hardware_online
    assert not session.state.pumps["P-201"].hardware_online

    # Simulate Arduino 1 connecting for P-201
    res = session.update_hardware_node(dev_id=1, pump_id="P-201", online=True)
    assert res["pump"] == "P-201"
    assert res["available"] is True
    assert res["run_state"] == RUNNING

    p201 = session.state.pumps["P-201"]
    assert p201.hardware_online is True
    assert p201.available is True


def test_hardware_disconnect_stops_pump_and_triggers_standby():
    # Make sure duty P-203 is running and hardware online
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=True)
    assert session.state.pumps["P-203"].run_state == RUNNING
    assert session.state.pumps["P-204"].run_state == STOPPED

    # Disconnect physical Arduino 2 (USB unplugged)
    res = session.update_hardware_node(dev_id=2, pump_id="P-203", online=False)
    assert res["available"] is False
    assert res["run_state"] == STOPPED

    p203 = session.state.pumps["P-203"]
    assert p203.hardware_online is False
    assert p203.available is False
    assert p203.run_state == STOPPED

    # Standby pump P-204 should immediately trigger STARTING (auto-start)
    p204 = session.state.pumps["P-204"]
    assert p204.run_state in (STARTING, RUNNING)
    assert p204.auto_started is True


def test_hardware_reconnect_restores_duty():
    # Start with P-203 disconnected
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=False)
    assert session.state.pumps["P-203"].available is False

    # Reconnect P-203
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=True)
    p203 = session.state.pumps["P-203"]
    assert p203.hardware_online is True
    assert p203.available is True
    assert p203.run_state in (RUNNING, STARTING)


def test_knob_adjusts_pump_health():
    # Connect and dial knob to 0.40 (wear / throttle)
    res = session.update_hardware_node(dev_id=2, pump_id="P-203", online=True, knob=0.40)
    assert res["health"] == 0.40
    p203 = session.state.pumps["P-203"]
    assert p203.health == 0.40
    assert p203.knob_factor == 0.40

    # Dial knob back to 0.95
    res = session.update_hardware_node(dev_id=2, pump_id="P-203", online=True, knob=0.95)
    assert res["health"] == 0.95
    assert session.state.pumps["P-203"].health == 0.95


def test_thermal_overheat_trips_pump():
    # Normal temperature 45 C
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=True, temperature_c=45.0)
    assert session.state.pumps["P-203"].run_state != TRIPPED
    assert session.state.pumps["P-203"].temperature_c == 45.0

    # Critical overheat temperature 89.2 C
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=True, temperature_c=89.2)
    p203 = session.state.pumps["P-203"]
    assert p203.temperature_c == 89.2
    assert p203.run_state == TRIPPED

    # Cool down to 50 C clears overheat
    session.update_hardware_node(dev_id=2, pump_id="P-203", online=True, temperature_c=50.0)
    assert not any("Thermal overheat" in str(f.params.get("reason", "")) for f in session.state.faults)


def test_api_hardware_endpoints():
    client = TestClient(app)

    # 1. Post telemetry for Device 1 (P-201)
    resp = client.post("/api/hardware/status", json={
        "dev": 1,
        "pump": "P-201",
        "online": True,
        "knob": 0.75,
        "temperature_c": 38.5,
        "light_level": 512.0,
        "telemetry": {"caps": ["matrix", "knob", "temp", "buzzer"]}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["result"]["pump"] == "P-201"
    assert data["result"]["health"] == 0.75

    # 2. Query hardware summary
    get_resp = client.get("/api/hardware/status")
    assert get_resp.status_code == 200
    summary = get_resp.json()
    assert "1" in summary["nodes"]
    assert summary["nodes"]["1"]["online"] is True
    assert summary["nodes"]["1"]["temperature_c"] == 38.5
    assert summary["nodes"]["1"]["knob_factor"] == 0.75
    assert summary["active_pumps"]["P-201"]["online"] is True
