import pytest
from dataclasses import replace

from app import flow
from app.models import load_config
from app.forecast import closed_form_time_to_limit, rollout, tank_forecasts
from app.sim import initial_state, step
from app.state import RUNNING, STOPPED, TRIPPED
from .conftest import fault, run


def alloc(topo, **kw):
    base = dict(
        volumes={t: 500 for t in topo.tanks}, pump_on={p: False for p in topo.pumps}, pump_w={p: 1.0 for p in topo.pumps},
        pump_model_cfg=load_config().pump_model, pipeline_cap={"LOOP-A": 250, "LOOP-B": 250}, pipeline_r={"LOOP-A": 1.0, "LOOP-B": 1.0},
        treatment_cap={"HRJ-1": 400},
        source_rate={s: 0 for s in topo.sources}, dt_h=1 / 60)
    base.update(kw)
    return flow.allocate(topo, **base)


def test_pipeline_cap_limits_combined_pumps(topo):
    r = alloc(topo, pump_on={"CHP-1": True, "CHP-2": True, "CHP-3": False})
    assert r.pipeline_flow["LOOP-A"] == pytest.approx(250)  # 400 demanded, cap 250
    assert r.pump_flow["CHP-1"] == pytest.approx(125) and r.pump_flow["CHP-2"] == pytest.approx(125)
    assert r.pump_limited_by["CHP-1"] == "pipeline"


def test_unavailable_pump_zero_flow(topo, scene):
    state, cfg = scene("scene3_backup_unavailable")
    s = run(state, topo, cfg, 10)
    assert s.flows.pump_flow["CHP-2"] == 0 and s.pumps["CHP-2"].run_state == STOPPED


def test_treatment_constraint_scales_pipelines_proportionally(topo):
    r = alloc(topo, pump_on={"CHP-1": True, "CHP-3": True, "CHP-2": False}, treatment_cap={"HRJ-1": 200})
    assert r.pipeline_flow["LOOP-A"] == pytest.approx(100, rel=1e-3) and r.pipeline_flow["LOOP-B"] == pytest.approx(100, rel=1e-3)
    r = alloc(topo, pump_on={"CHP-1": True, "CHP-2": True, "CHP-3": True}, treatment_cap={"HRJ-1": 200})
    assert r.pipeline_flow["LOOP-A"] / r.pipeline_flow["LOOP-B"] == pytest.approx(250 / 200, rel=1e-3)  # proportional to demand
    assert r.treatment_flow["HRJ-1"] == pytest.approx(200)


def test_throttled_never_negative(topo):
    r = alloc(topo, pump_on={"CHP-1": True, "CHP-2": False, "CHP-3": False}, pipeline_cap={"LOOP-A": 0, "LOOP-B": 0})
    assert r.pump_flow["CHP-1"] == 0


def test_closed_form_regression_via_rollout(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    assert closed_form_time_to_limit(880, 950, 180, 90) == pytest.approx(46.67, abs=0.01)
    fc = tank_forecasts(rollout(state, topo, cfg), topo, cfg)
    assert fc["HALL-A"].time_to_HH == pytest.approx(46.67, abs=0.05)
    assert fc["HALL-A"].time_to_H == pytest.approx(13.33, abs=0.05)


def test_no_breach_when_net_non_positive_and_already_breached(topo, scene):
    assert closed_form_time_to_limit(880, 950, 90, 90) is None
    assert closed_form_time_to_limit(960, 950, 180, 90) == 0.0
    state, cfg = scene("scene1_normal")
    assert tank_forecasts(rollout(state, topo, cfg), topo, cfg)["HALL-A"].time_to_HH is None


def test_overflow_clamps_and_logs(topo, cfg):
    from app.models import patch_config
    cfg = patch_config(cfg, {"interlock": {"enabled": False}})
    s = initial_state(topo, cfg, {"tanks": {"HALL-A": 999}}, (fault("F1", "PUMP_TRIP", "CHP-1"), fault("F2", "PUMP_TRIP", "CHP-2")))
    s = run(s, topo, cfg, 3)
    assert s.tanks["HALL-A"].volume_bbl == 1000 and s.overflow_bbl["HALL-A"] > 0 and s.overflow_events["HALL-A"] == 1


def test_determinism(topo, scene):
    state, cfg = scene("scene4_pump_trip")
    a, b = run(state, topo, cfg, 90), run(state, topo, cfg, 90)
    assert a.tanks["HALL-A"].volume_bbl == b.tanks["HALL-A"].volume_bbl and a.pumps == b.pumps


def test_forecast_ignores_future_scripted_faults(topo, scene):
    state, cfg = scene("scene4_pump_trip")
    assert tank_forecasts(rollout(state, topo, cfg), topo, cfg)["HALL-A"].time_to_HH is None
