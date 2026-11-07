import random
from dataclasses import replace

import pytest

from app import actions as act
from app import faults
from app.decision import recommend
from app.forecast import rollout
from app.state import PipelineState
from .conftest import fault, run


def opts(rec):
    return {o.action_id: o for o in rec.options}


def test_scene2_recommends_standby_and_recovers(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    rec = recommend(state, topo, cfg)
    assert rec.best_option_id == "START_STANDBY_PUMP:P-204"
    assert 200 < opts(rec)[rec.best_option_id].cost_breakdown.total < 300  # "about $250"
    assert rec.do_nothing_cost >= opts(rec)[rec.best_option_id].cost_breakdown.total
    state = act.schedule(state, act.from_id(rec.best_option_id), cfg)
    s = run(state, topo, cfg, 120)
    assert s.trip_counts["T-104"] == 0 and max(s.tanks["T-104"].volume_bbl for _ in [0]) < cfg.limits.HH


def test_truck_rejected_for_lead_time(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    o = opts(recommend(state, topo, cfg))["DISPATCH_TRUCK:T-104"]
    assert not o.feasible and "LEAD_TIME_EXCEEDS_DEADLINE" in o.reason_codes


def test_scene3_reranks_and_rejects_backup(topo, scene):
    state, cfg = scene("scene3_backup_unavailable")
    rec = recommend(state, topo, cfg)
    assert "ASSET_UNAVAILABLE" in opts(rec)["START_STANDBY_PUMP:P-204"].reason_codes
    assert rec.best_option_id == "REDUCE_PRODUCTION:SRC-1:50"
    assert rec.do_nothing_cost >= opts(rec)[rec.best_option_id].cost_breakdown.total


def test_override_marks_top_pick_unavailable(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    top = recommend(state, topo, cfg).best_option_id
    rec2 = recommend(state, topo, cfg, unavailable_overrides={"P-204"})
    assert rec2.best_option_id != top and top not in rec2.ranked_option_ids
    assert recommend(state, topo, cfg).best_option_id == top  # stateless: no hidden memory


def test_determinism(topo, scene):
    state, cfg = scene("scene5_treatment_constraint")
    a, b = recommend(state, topo, cfg), recommend(state, topo, cfg)
    assert a.model_dump() == b.model_dump()


def test_pipeline_restriction_rejects_pump_start(topo, scene):
    state, cfg = scene("scene2_pump_degraded")
    state = replace(state, faults=state.faults + (fault("R", "PIPELINE_RESTRICTION", "PL-1", factor=0.3),))
    o = opts(recommend(state, topo, cfg))["START_STANDBY_PUMP:P-204"]
    assert "PIPELINE_CAP_EXCEEDED" in o.reason_codes


def test_scene5_multi_tank_uses_pairs_and_flags_downstream(topo, scene):
    state, cfg = scene("scene5_treatment_constraint")
    rec = recommend(state, topo, cfg)
    assert rec.affected_assets.first_to_limit == "T-104"
    assert rec.best_option_id and "+" in rec.best_option_id
    assert "MOVES_PROBLEM_DOWNSTREAM" in opts(rec)["START_STANDBY_PUMP:P-204"].reason_codes


def test_no_risk_means_no_action(topo, scene):
    state, cfg = scene("scene1_normal")
    rec = recommend(state, topo, cfg)
    assert rec.status == "normal" and rec.best_option_id == act.DO_NOTHING and rec.ranked_option_ids == []


def test_property_recommended_options_satisfy_hard_constraints(topo, cfg, scene):
    rnd = random.Random(7)
    base, cfg = scene("scene1_normal")
    for i in range(12):
        fl = []
        if rnd.random() < .6:
            fl.append(fault("a", "PUMP_DEGRADE", "P-203", factor=rnd.choice([.3, .45, .6])))
        if rnd.random() < .4:
            fl.append(fault("b", "PIPELINE_RESTRICTION", "PL-1", factor=rnd.choice([.3, .5, .8])))
        if rnd.random() < .4:
            fl.append(fault("c", "TREATMENT_CONSTRAINT", "TRT-1", factor=rnd.choice([.4, .6, .8])))
        if rnd.random() < .3:
            fl.append(fault("d", "PUMP_UNAVAILABLE", "P-204"))
        if rnd.random() < .3:
            fl.append(fault("e", "INFLOW_SURGE", "SRC-1", multiplier=rnd.choice([1.2, 1.5])))
        tanks = {"T-104": rnd.randint(300, 900), "T-101": rnd.randint(300, 900)}
        state = replace(base, faults=tuple(fl), tanks={k: replace(v, volume_bbl=float(tanks.get(k, v.volume_bbl)), reported_bbl=float(tanks.get(k, v.volume_bbl)), reported_lo_bbl=float(tanks.get(k, v.volume_bbl))) for k, v in base.tanks.items()})
        rec = recommend(state, topo, cfg)
        for oid in rec.ranked_option_ids:
            o = opts(rec)[oid]
            assert o.feasible and not o.reason_codes
            assert o.margin_bbl >= cfg.decision.min_margin_bbl
            traj = rollout(state, topo, cfg, act.combo_from_id(oid))
            assert not any(traj.trips.values()) and not any(traj.overflow_events.values())
            assert max(max(v) for v in traj.volumes.values()) <= cfg.limits.HH - cfg.decision.min_margin_bbl + 1e-6
            for a in act.combo_from_id(oid):
                eff = faults.effective(state, topo)
                assert not act.preconditions(a, state, eff, topo, cfg, 1 / 60)
        # DO_NOTHING is always present as the reference row
        assert act.DO_NOTHING in opts(rec)
        costs = [opts(rec)[o].cost_breakdown.total for o in rec.ranked_option_ids]
        assert costs == sorted(costs)
