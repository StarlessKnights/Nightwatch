import math
from dataclasses import replace

import pytest

from app import diagnosis, pump_model as pmod
from app.forecast import rollout, tank_forecasts
from app.sim import initial_state, step
from .conftest import fault, run


def test_healthy_point(cfg):
    q, p = pmod.operating_point(1, 1, 1, cfg.pump_model)
    assert q == pytest.approx(200, abs=0.1) and p == pytest.approx(55.6, abs=0.1)


def test_wear_and_restriction_same_flow_opposite_pressure(cfg):
    q1, p1 = pmod.operating_point(0.299, 1, 1.0, cfg.pump_model)
    q2, p2 = pmod.operating_point(1.0, 1, 9.9, cfg.pump_model)
    assert q1 == pytest.approx(90.0, abs=0.2) and p1 == pytest.approx(27.2, abs=0.2)
    assert q2 == pytest.approx(90.0, abs=0.5) and p2 == pytest.approx(91.0, abs=0.5)
    assert p1 < 55.6 < p2
    assert diagnosis.diagnose([{"Q": q1, "P": p1, "s": 1}], cfg)["code"] == "PUMP_WEAR"
    assert diagnosis.diagnose([{"Q": q2, "P": p2, "s": 1}], cfg)["code"] == "RESTRICTION"


@pytest.mark.parametrize("w,r", [(0.3, 1.0), (0.6, 1.0), (1.0, 5.0), (1.0, 9.9), (0.5, 4.0), (0.85, 1.0)])
def test_inversion_round_trip(cfg, w, r):
    q, p = pmod.operating_point(w, 1, r, cfg.pump_model)
    w_est, r_est = diagnosis.invert(q, p, 1, cfg)
    assert w_est == pytest.approx(w, rel=0.01) and r_est == pytest.approx(r, rel=0.01)


def test_monotone(cfg):
    pm = cfg.pump_model
    qs = [pmod.operating_point(w / 20, 1, 1, pm)[0] for w in range(20, 0, -1)]
    assert all(a >= b for a, b in zip(qs, qs[1:]))
    qs = [pmod.operating_point(1, 1, 1 + i * 0.5, pm)[0] for i in range(25)]
    assert all(a >= b for a, b in zip(qs, qs[1:]))


def test_dead_head_no_nan(cfg):
    pm = cfg.pump_model
    for w, s, r in [(1, 0, 1), (0, 1, 1), (0.1, 1, 1), (1, 0.4, 1), (0.2, 0.5, 20)]:
        q, p = pmod.operating_point(w, s, r, pm)
        assert q == 0.0 and p == 0.0 and not math.isnan(q)
    d = diagnosis.diagnose([{"Q": 0, "P": 0, "s": 0}], cfg)
    assert d["code"] == "FLOW_TOO_LOW" and d["w_est"] is None


def test_compound_and_none(cfg):
    q, p = pmod.operating_point(0.6, 1, 6.0, cfg.pump_model)
    assert diagnosis.diagnose([{"Q": q, "P": p, "s": 1}], cfg)["code"] == "COMPOUND"
    q, p = pmod.operating_point(1.0, 1, 1.0, cfg.pump_model)
    assert diagnosis.diagnose([{"Q": q, "P": p, "s": 1}], cfg)["code"] == "NONE"


def test_scene2_regression_through_rollout(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    assert tank_forecasts(rollout(state, topo, cfg), topo, cfg)["T-104"].time_to_HH == pytest.approx(46.7, abs=0.1)


def test_mass_conservation_per_tank(topo, scene):
    state, cfg = scene("scene5_treatment_constraint")
    s = state
    for _ in range(60):
        before = {t: x.volume_bbl for t, x in s.tanks.items()}
        s = step(s, topo, cfg)
        for t, x in s.tanks.items():
            net = (s.flows.tank_inflow[t] - s.flows.tank_outflow[t]) / 60
            assert x.volume_bbl == pytest.approx(before[t] + net, abs=1e-6)


def test_restriction_limits_both_pumps(topo, scene):
    state, cfg = scene("scene1_normal")
    state = replace(state, faults=(fault("R", "PIPELINE_RESTRICTION", "PL-1", r=9.9),),
                    pumps={**state.pumps, "P-204": replace(state.pumps["P-204"], run_state="RUNNING")})
    s = step(state, topo, cfg)
    assert s.flows.pipeline_flow["PL-1"] < 100  # second pump behind a blocked line adds ~nothing
