"""Unit and integration tests for Winstead Cyber Incident Command Core.

Verifies:
- NIST SP 800-61 lifecycle stages
- Hardware authentication and responder access control
- Air-gap isolation protocol & external egress severing
- Compromised asset scope definitions
- Out-of-band communication feed
- FastAPI REST endpoints
- WebSocket /ws/sim incident state broadcasting
"""
import pytest
from starlette.testclient import TestClient

from app.cyber_incident import (
    AssetCategory,
    AssetCompromiseStatus,
    CyberIncidentManager,
    NISTStage,
    ROLE_BADGES,
    ResponderRole,
)
from app.main import app, session


@pytest.fixture(autouse=True)
def reset_session_fixture():
    session.reset()
    yield
    session.reset()


# ==============================================================================
# Pure Manager Unit Tests
# ==============================================================================


def test_cyber_incident_manager_initial_state():
    mgr = CyberIncidentManager()
    assert mgr.airgap_engaged is False
    assert mgr.quarantined_egress is False
    assert mgr.is_egress_allowed() is True
    assert mgr.stage == NISTStage.DETECTION.value
    assert mgr.incident_level == "CRITICAL"
    assert len(mgr.responders) == 0
    assert len(mgr.comms_feed) == 0
    assert len(mgr.event_log) == 0

    scope = mgr.get_scope()
    assert len(scope) == 4
    for asset in AssetCategory:
        assert asset.value in scope
        assert scope[asset.value]["status"] == AssetCompromiseStatus.HEALTHY.value


def test_airgap_toggle_and_isolation():
    mgr = CyberIncidentManager()
    assert mgr.is_egress_allowed() is True
    mgr.assert_egress_allowed()  # should not raise

    # Engage airgap (Winstead #1: Secure & Isolated)
    res = mgr.toggle_airgap(engaged=True, source="sec_ops")
    assert res["airgap_engaged"] is True
    assert res["quarantined_egress"] is True
    assert mgr.airgap_engaged is True
    assert mgr.quarantined_egress is True
    assert mgr.is_egress_allowed() is False

    with pytest.raises(PermissionError, match="External API egress is severed/quarantined"):
        mgr.assert_egress_allowed()

    # Verify event logged
    assert len(mgr.event_log) == 1
    assert mgr.event_log[0]["action"] == "AIRGAP_ENGAGED"
    assert mgr.event_log[0]["actor"] == "sec_ops"

    # Disengage airgap
    res_dis = mgr.toggle_airgap(engaged=False, source="incident_commander")
    assert res_dis["airgap_engaged"] is False
    assert res_dis["quarantined_egress"] is False
    assert mgr.airgap_engaged is False
    assert mgr.is_egress_allowed() is True
    mgr.assert_egress_allowed()
    assert len(mgr.event_log) == 2
    assert mgr.event_log[1]["action"] == "AIRGAP_DISENGAGED"


def test_responder_access_control_and_auth():
    mgr = CyberIncidentManager()

    # Valid responder with hardware token
    resp1 = mgr.add_responder(
        name="Sarah Connor",
        role="incident_commander",
        verified=True,
        hardware_token="HW-TOKEN-994",
    )
    assert resp1["name"] == "Sarah Connor"
    assert resp1["role"] == "incident_commander"
    assert resp1["role_badge"] == "INCIDENT-COMMAND"
    assert resp1["hardware_token"] == "HW-TOKEN-994"
    assert resp1["verified"] is True
    assert mgr.verify_responder(resp1["id"]) is True

    # Valid operator
    resp2 = mgr.add_responder(name="Alex Murphy", role="operator")
    assert resp2["role_badge"] == "OPS-STATION"
    assert resp2["hardware_token"].startswith("HW-AUTH-")

    # Valid admin
    resp3 = mgr.add_responder(name="Neo", role="admin")
    assert resp3["role_badge"] == "ADMIN-AUTH"

    assert len(mgr.get_responders()) == 3

    # Invalid role rejection
    with pytest.raises(ValueError, match="Invalid role"):
        mgr.add_responder(name="Hacker", role="intruder")

    # Empty name rejection
    with pytest.raises(ValueError, match="name cannot be empty"):
        mgr.add_responder(name="", role="operator")


def test_nist_stages_and_lifecycle():
    mgr = CyberIncidentManager()
    assert mgr.stage == NISTStage.DETECTION.value

    # Transition to CONTAINMENT
    res = mgr.set_stage("CONTAINMENT", source="lead_sec")
    assert res["stage"] == NISTStage.CONTAINMENT.value
    assert res["previous_stage"] == NISTStage.DETECTION.value
    assert mgr.stage == NISTStage.CONTAINMENT.value

    # Transition to ERADICATION
    res = mgr.set_stage("ERADICATION")
    assert res["stage"] == NISTStage.ERADICATION.value

    # Transition to RECOVERY
    res = mgr.set_stage("RECOVERY")
    assert res["stage"] == NISTStage.RECOVERY.value

    # Invalid stage rejection
    with pytest.raises(ValueError, match="Invalid NIST stage"):
        mgr.set_stage("PANIC_MODE")


def test_asset_compromised_scope():
    mgr = CyberIncidentManager()

    # Degrade CHILLED_WATER_LOOP
    up1 = mgr.update_asset_scope(
        asset="CHILLED_WATER_LOOP",
        status="DEGRADED",
        notes="Thermal spike observed in primary coolant line",
        actor="ops_lead",
    )
    assert up1["ok"] is True
    assert up1["status"] == "DEGRADED"

    # Lock COMPUTE_POD_A with ransomware
    up2 = mgr.update_asset_scope(
        asset="COMPUTE_POD_A",
        status="LOCKED_RANSOMWARE",
        notes="Host encrypted by BlackCat payload",
        actor="threat_intel",
    )
    assert up2["status"] == "LOCKED_RANSOMWARE"

    # Exfiltrate EXTERNAL_WAN
    up3 = mgr.update_asset_scope(
        asset="EXTERNAL_WAN",
        status="DATA_EXFILTRATED",
        notes="Outbound spike to anomalous C2 IP",
        actor="net_analyst",
    )
    assert up3["status"] == "DATA_EXFILTRATED"

    scope = mgr.get_scope()
    assert scope["CHILLED_WATER_LOOP"]["status"] == "DEGRADED"
    assert scope["COMPUTE_POD_A"]["status"] == "LOCKED_RANSOMWARE"
    assert scope["EXTERNAL_WAN"]["status"] == "DATA_EXFILTRATED"
    assert scope["STORAGE_SAN"]["status"] == "HEALTHY"

    # Invalid asset category
    with pytest.raises(ValueError, match="Invalid asset category"):
        mgr.update_asset_scope("OFFICE_LAPTOP", "DEGRADED")

    # Invalid status
    with pytest.raises(ValueError, match="Invalid compromise status"):
        mgr.update_asset_scope("STORAGE_SAN", "BURNED_OUT")


def test_out_of_band_real_time_comms():
    mgr = CyberIncidentManager()

    # Post commander directive
    msg1 = mgr.post_comms_message(
        author="Cmdr. Vance",
        role="incident_commander",
        message="Initiate air-gap isolation immediately.",
    )
    assert msg1["id"] == 1
    assert msg1["author"] == "Cmdr. Vance"
    assert msg1["role"] == "incident_commander"
    assert msg1["role_badge"] == "INCIDENT-COMMAND"
    assert "timestamp" in msg1

    # Post operator reply
    msg2 = mgr.post_comms_message(
        author="Tech Miller",
        role="operator",
        message="Pumps P-201 and P-202 transitioned to local manual override.",
    )
    assert msg2["id"] == 2
    assert msg2["role_badge"] == "OPS-STATION"

    feed = mgr.get_comms_feed()
    assert len(feed) == 2
    assert feed[0]["id"] == 1
    assert feed[1]["id"] == 2

    # Validation errors
    with pytest.raises(ValueError, match="Message cannot be empty"):
        mgr.post_comms_message("Cmdr. Vance", "incident_commander", "   ")

    with pytest.raises(ValueError, match="Invalid role"):
        mgr.post_comms_message("Cmdr. Vance", "contractor", "Test")


def test_status_summary_and_reset():
    mgr = CyberIncidentManager()
    mgr.toggle_airgap(True, source="admin")
    mgr.add_responder("Alice", "admin")
    mgr.update_asset_scope("COMPUTE_POD_A", "LOCKED_RANSOMWARE")
    mgr.post_comms_message("Alice", "admin", "Critical alert")

    status = mgr.get_status()
    assert status["airgap_engaged"] is True
    assert status["quarantined_egress"] is True
    assert status["active_incident_level"] == "CRITICAL"
    assert status["stage"] == "DETECTION"
    assert status["responder_count"] == 1
    assert status["scope"]["COMPUTE_POD_A"] == "LOCKED_RANSOMWARE"
    assert status["scope_summary"]["locked_ransomware"] == 1
    assert status["scope_summary"]["healthy"] == 3
    assert status["comms_count"] == 1
    assert status["events_count"] >= 3

    # Test reset
    mgr.reset()
    assert mgr.airgap_engaged is False
    assert mgr.quarantined_egress is False
    assert mgr.responder_count == 0 or len(mgr.responders) == 0
    assert len(mgr.comms_feed) == 0
    assert len(mgr.event_log) == 0
    assert mgr.scope["COMPUTE_POD_A"]["status"] == "HEALTHY"


# ==============================================================================
# FastAPI REST Endpoints Integration Tests
# ==============================================================================


def test_api_incident_status_endpoint():
    client = TestClient(app)
    resp = client.get("/api/incident/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "airgap_engaged" in data
    assert data["airgap_engaged"] is False
    assert data["active_incident_level"] == "CRITICAL"
    assert data["stage"] == "DETECTION"
    assert data["responder_count"] == 0
    assert "scope" in data
    assert "scope_summary" in data


def test_api_incident_airgap_endpoint():
    client = TestClient(app)

    # 1. Engage air-gap
    resp = client.post("/api/incident/airgap", json={"engaged": True, "source": "command_terminal"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["airgap_engaged"] is True
    assert data["quarantined_egress"] is True
    assert data["source"] == "command_terminal"
    assert "timestamp" in data

    # Verify reflected in session
    assert session.incident.airgap_engaged is True
    assert session.incident.quarantined_egress is True

    # Check status endpoint
    status_resp = client.get("/api/incident/status")
    assert status_resp.json()["airgap_engaged"] is True

    # 2. Disengage air-gap
    resp_dis = client.post("/api/incident/airgap", json={"engaged": False, "source": "incident_commander"})
    assert resp_dis.status_code == 200
    assert resp_dis.json()["airgap_engaged"] is False
    assert session.incident.airgap_engaged is False


def test_api_incident_scope_endpoints():
    client = TestClient(app)

    # 1. Get initial scope
    get_resp = client.get("/api/incident/scope")
    assert get_resp.status_code == 200
    scope = get_resp.json()
    assert "COMPUTE_POD_A" in scope
    assert scope["COMPUTE_POD_A"]["status"] == "HEALTHY"

    # 2. Update asset scope
    post_resp = client.post(
        "/api/incident/scope",
        json={
            "asset": "COMPUTE_POD_A",
            "status": "LOCKED_RANSOMWARE",
            "notes": "Ransomware signature detected on controller",
            "actor": "forensics_lead",
        },
    )
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["ok"] is True
    assert post_data["asset"] == "COMPUTE_POD_A"
    assert post_data["status"] == "LOCKED_RANSOMWARE"
    assert post_data["scope"]["COMPUTE_POD_A"]["status"] == "LOCKED_RANSOMWARE"

    # 3. Invalid asset category -> 400
    bad_asset_resp = client.post(
        "/api/incident/scope",
        json={"asset": "INVALID_ASSET", "status": "HEALTHY"},
    )
    assert bad_asset_resp.status_code == 400

    # 4. Invalid status -> 400
    bad_status_resp = client.post(
        "/api/incident/scope",
        json={"asset": "STORAGE_SAN", "status": "COMPLETELY_GONE"},
    )
    assert bad_status_resp.status_code == 400


def test_api_incident_responders_endpoints():
    client = TestClient(app)

    # 1. Add responder
    resp = client.post(
        "/api/incident/responders",
        json={
            "name": "David Bowman",
            "role": "incident_commander",
            "verified": True,
            "hardware_token": "YUBIKEY-NIGHTWATCH-1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "David Bowman"
    assert data["role"] == "incident_commander"
    assert data["role_badge"] == "INCIDENT-COMMAND"
    assert data["verified"] is True
    assert data["hardware_token"] == "YUBIKEY-NIGHTWATCH-1"

    # 2. List responders
    list_resp = client.get("/api/incident/responders")
    assert list_resp.status_code == 200
    responders = list_resp.json()
    assert len(responders) == 1
    assert responders[0]["id"] == data["id"]

    # 3. Verify status responder count increased
    status_resp = client.get("/api/incident/status")
    assert status_resp.json()["responder_count"] == 1

    # 4. Invalid role -> 400
    bad_resp = client.post(
        "/api/incident/responders",
        json={"name": "Unknown Person", "role": "bystander"},
    )
    assert bad_resp.status_code == 400


def test_api_incident_comms_endpoints():
    client = TestClient(app)

    # 1. Post out-of-band comms message
    post_resp = client.post(
        "/api/incident/comms",
        json={
            "author": "Operator Jax",
            "role": "operator",
            "message": "Physical network cord pulled from WAN uplink switch.",
        },
    )
    assert post_resp.status_code == 200
    data = post_resp.json()
    assert data["id"] == 1
    assert data["author"] == "Operator Jax"
    assert data["role"] == "operator"
    assert data["role_badge"] == "OPS-STATION"
    assert "timestamp" in data

    # 2. Get comms feed
    get_resp = client.get("/api/incident/comms")
    assert get_resp.status_code == 200
    feed = get_resp.json()
    assert len(feed) == 1
    assert feed[0]["id"] == 1
    assert feed[0]["message"] == "Physical network cord pulled from WAN uplink switch."

    # 3. Bad message -> 400
    bad_msg = client.post(
        "/api/incident/comms",
        json={"author": "Jax", "role": "operator", "message": "   "},
    )
    assert bad_msg.status_code == 400


def test_api_incident_stage_and_events():
    client = TestClient(app)

    # Transition stage
    stage_resp = client.post("/api/incident/stage", json={"stage": "CONTAINMENT", "source": "lead"})
    assert stage_resp.status_code == 200
    assert stage_resp.json()["stage"] == "CONTAINMENT"
    assert stage_resp.json()["previous_stage"] == "DETECTION"

    # Invalid stage -> 400
    bad_stage = client.post("/api/incident/stage", json={"stage": "UNKNOWN_STAGE"})
    assert bad_stage.status_code == 400

    # Events endpoint
    events_resp = client.get("/api/incident/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 1
    assert any(e["action"] == "STAGE_TRANSITION" for e in events)


# ==============================================================================
# WebSocket Incident State Integration Test
# ==============================================================================


def test_websocket_sim_includes_incident_state():
    client = TestClient(app)

    # Set up some incident state
    session.incident.toggle_airgap(True, source="admin_ws_test")
    session.incident.update_asset_scope("COMPUTE_POD_A", "DEGRADED")

    # Connect to WebSocket /ws/sim
    with client.websocket_connect("/ws/sim") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "sync"
        assert "incident" in msg
        incident = msg["incident"]
        assert incident["airgap_engaged"] is True
        assert incident["quarantined_egress"] is True
        assert incident["active_incident_level"] == "CRITICAL"
        assert incident["stage"] == "DETECTION"
        assert incident["scope"]["COMPUTE_POD_A"] == "DEGRADED"

        # Also state has airgap_engaged
        assert "state" in msg
        assert msg["state"]["airgap_engaged"] is True
