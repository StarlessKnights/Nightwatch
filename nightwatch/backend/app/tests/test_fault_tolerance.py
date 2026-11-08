import pytest
from dataclasses import replace

from app import alarms, interlock
from app.models import patch_config
from app.sim import initial_state, step
from app.state import RUNNING, STARTING, STOPPED, TRIPPED, AUTO
from .conftest import fault, run


def test_trip_standby_running_after_exact_delay(topo, scene):
    state, cfg = scene("scene4_pump_trip")
    delay = cfg.control.standby_start_delay_min
    s = run(state, topo, cfg, 5)  # t=5: trip fault becomes active on the next tick
    assert s.pumps["CHP-2"].run_state == STOPPED
    s = step(s, topo, cfg)  # tick at t=5
    assert s.pumps["CHP-1"].run_state == TRIPPED and s.pumps["CHP-2"].run_state == STARTING
    assert any(e.code == "STANDBY_AUTOSTART" and e.tag == AUTO for e in s.new_events)
    s = run(s, topo, cfg, delay - 1)
    assert s.pumps["CHP-2"].run_state == STARTING
    s = step(s, topo, cfg)
    assert s.pumps["CHP-2"].run_state == RUNNING and s.t_min == 5 + delay + 1


def test_degrade_changeover_only_with_flag(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    assert run(state, topo, cfg, 10).pumps["CHP-2"].run_state == STOPPED
    state, cfg = scene("scene2_pump_degraded", control={"auto_changeover_on_low_flow": True})
    s = run(state, topo, cfg, 3 + 1 + cfg.control.standby_start_delay_min + 1)
    assert s.pumps["CHP-2"].run_state == RUNNING and s.pumps["CHP-2"].auto_started


def test_unavailable_pump_never_auto_started(topo, scene):
    state, cfg = scene("scene3_backup_unavailable", control={"auto_changeover_on_low_flow": True})
    state = replace(state, faults=state.faults + (fault("T", "PUMP_TRIP", "CHP-1", start=0),))
    s = run(state, topo, cfg, 30)
    assert s.pumps["CHP-2"].run_state == STOPPED


def test_hh_load_shed_ramps_and_restores(topo, scene):
    state, cfg = scene("scene6_interlock_only", interlock={"shed_ramp_min": 3})
    trip = None
    shed = []
    for _ in range(120):
        state = step(state, topo, cfg)
        pct = state.sources["LOAD-A"].shed_pct
        if trip is None and state.interlocks["HALL-A"].tripped:
            trip = state.t_min
        if trip is not None and len(shed) < 4:
            shed.append(round(pct))
    assert shed == [33, 67, 100, 100]  # staged, not an instant cut


def test_hh_interlock_without_decision_engine(topo, scene):
    state, cfg = scene("scene6_interlock_only")
    s = run(state, topo, cfg, 60)
    assert s.interlocks["HALL-A"].tripped and s.sources["LOAD-A"].shut_in
    assert max(ts.volume_bbl for ts in [s.tanks["HALL-A"]]) < cfg.limits.HH + 5
    # independence: static check on the module's imports
    import ast, pathlib
    src = ast.parse(pathlib.Path(interlock.__file__).read_text())
    imported = {n.module for n in ast.walk(src) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"decision", "actions", "forecast", "sim", "control"}


def test_interlock_releases_only_below_reset(topo, scene):
    state, cfg = scene("scene6_interlock_only")
    s = run(state, topo, cfg, 60)
    assert s.interlocks["HALL-A"].tripped
    released_at = None
    for _ in range(300):
        s = step(s, topo, cfg)
        if not s.interlocks["HALL-A"].tripped:
            released_at = s.tanks["HALL-A"].reported_bbl
            break
    assert released_at is not None and released_at < cfg.limits.hh_reset_bbl


def test_ll_trips_pump_dry_run_protection(topo, cfg):
    s = initial_state(topo, cfg, {"tanks": {"HALL-A": 60}, "sources": {"LOAD-A": 0}})
    s = run(s, topo, cfg, 8)
    assert s.interlocks["HALL-A"].ll_tripped
    assert s.pumps["CHP-1"].run_state == TRIPPED
    assert s.pumps["CHP-2"].run_state != RUNNING  # standby must not be started into a dry tank


def test_alarm_deadband_and_on_delay_prevent_chatter(topo, cfg):
    cfg = patch_config(cfg, {"limits": {"on_delay_min": 2}})
    s = initial_state(topo, cfg, {"tanks": {"HALL-A": 600}})
    raised = 0
    for k in range(40):
        noisy = 903 if k % 2 == 0 else 897  # chatters around H=900 every minute
        ts = replace(s.tanks["HALL-A"], reported_bbl=noisy, reported_lo_bbl=noisy)
        s = replace(s, tanks={**s.tanks, "HALL-A": ts})
        s, ev = alarms.alarm_pass(s, topo, cfg)
        raised += sum(1 for e in ev if e.code == "ALARM_RAISED" and e.params["condition"] == "H")
        s = replace(s, t_min=s.t_min + 1)
    assert raised == 0  # on-delay never satisfied: condition never persists 2 ticks
    for k in range(5):  # sustained high -> raises once
        ts = replace(s.tanks["HALL-A"], reported_bbl=905, reported_lo_bbl=905)
        s = replace(s, tanks={**s.tanks, "HALL-A": ts})
        s, ev = alarms.alarm_pass(s, topo, cfg)
        raised += sum(1 for e in ev if e.code == "ALARM_RAISED" and e.params["condition"] == "H")
        s = replace(s, t_min=s.t_min + 1)
    assert raised == 1
    h = [a for a in s.alarms if a.id == "HALL-A:H"]
    assert len(h) == 1
    ts = replace(s.tanks["HALL-A"], reported_bbl=895, reported_lo_bbl=895)  # inside deadband -> stays active
    s, _ = alarms.alarm_pass(replace(s, tanks={**s.tanks, "HALL-A": ts}), topo, cfg)
    assert next(a for a in s.alarms if a.id == "HALL-A:H").state != "CLEARED"
    ts = replace(s.tanks["HALL-A"], reported_bbl=885, reported_lo_bbl=885)
    s, _ = alarms.alarm_pass(replace(s, tanks={**s.tanks, "HALL-A": ts}), topo, cfg)
    assert next(a for a in s.alarms if a.id == "HALL-A:H").state == "CLEARED"


def test_sensor_disagreement_uses_higher_reading(topo, scene):
    state, cfg = scene("scene7_sensor_fault")
    s = run(state, topo, cfg, 10)
    ts = s.tanks["HALL-A"]
    assert ts.level_sensors["A"] == 400 and ts.reported_bbl > 400 and ts.reported_bbl == ts.level_sensors["B"]
    assert any(a.id == "HALL-A:SENSOR_DISAGREE" for a in s.alarms)


def test_alarms_do_not_change_physics(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    a, b = run(state, topo, cfg, 50), run(state, topo, cfg, 50, with_alarms=False)
    assert a.tanks["HALL-A"].volume_bbl == b.tanks["HALL-A"].volume_bbl
