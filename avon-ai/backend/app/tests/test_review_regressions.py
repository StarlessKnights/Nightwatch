import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.session import Session


@pytest.mark.parametrize(("kind", "target", "params", "end"), [
    ("PUMP_DEGRADE", "CHP-1", {"w": "failed"}, None),
    ("PUMP_DEGRADE", "CHP-1", {"w": float("nan")}, None),
    ("PUMP_TRIP", "CHP-1", {"unknown": True}, None),
    ("LEVEL_SENSOR_FAULT", "HALL-B", {"transmitter": "B"}, None),
    ("PUMP_TRIP", "CHP-1", {}, 0),
])
def test_invalid_live_fault_leaves_plant_unchanged(kind, target, params, end):
    session = Session()
    before = session.state, session.revision
    with pytest.raises(ValueError):
        session.inject_fault(kind, target, params, end)
    assert (session.state, session.revision) == before


def test_zero_timestep_does_not_break_next_forecast():
    session = Session()
    original = session.cfg
    with pytest.raises(ValidationError):
        session.patch_config({"time": {"dt_min": 0}})
    assert session.cfg is original
    session.advance()
    session.refresh_forecast()


def test_restart_rejects_old_approval_even_for_identical_scenario(monkeypatch):
    from app import main
    session = Session()
    monkeypatch.setattr(main, "session", session)
    session.load("scene2_pump_degraded")
    rec = asyncio.run(main.get_recommendation())
    assert rec["run_id"] == session.run_id and rec["best_option_id"]
    session.reset()
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.approve(rec["best_option_id"], rec["run_id"]))
    assert error.value.status_code == 409 and not session.state.pending_actions


def test_sibling_hall_is_not_first_to_limit_for_an_unconnected_pump():
    session = Session()
    session.load("scene2_pump_degraded")
    assert session.impact("CHP-1")["first_to_limit"] == "HALL-A"
    assert session.impact("CHP-3")["first_to_limit"] is None
