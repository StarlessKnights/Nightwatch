"""Time-stepped engine. `step()` is a PURE function: (state, topo, cfg, rng) -> state'."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import actions, alarms, control, faults, flow, interlock
from .models import Config
from .network import Topology
from .state import (AUTO, FAULT, OPERATOR, RUNNING, STARTING, STOPPED, SYSTEM, TRIPPED, Event, InterlockState,
                    PipelineState, PumpState, SimState, SourceState, TankState, TreatmentState)


def initial_state(topo: Topology, cfg: Config, initial: dict | None = None, scripted_faults: tuple = ()) -> SimState:
    """Build t=0 state from topology defaults plus scenario overrides."""
    init = initial or {}
    pump_over = init.get("pumps", {})
    tanks, pumps, sources, pipelines, treatment = {}, {}, {}, {}, {}
    for tid, info in topo.tanks.items():
        v = float(init.get("tanks", {}).get(tid, info.initial))
        tanks[tid] = TankState(v, {"A": v, "B": v} if info.redundant else {"A": v}, v, v)
    for pid, info in topo.pumps.items():
        o = pump_over.get(pid, {})
        pumps[pid] = PumpState(
            role=info.role, run_state=o.get("run_state", RUNNING if info.role == "duty" else STOPPED),
            capacity_factor=o.get("capacity_factor", 1.0), available=o.get("available", True))
    for sid in topo.sources:
        rate = init.get("sources", {}).get(sid, topo.nodes[sid]["rate_bbl_hr"])
        sources[sid] = SourceState(float(rate))
    for pl in topo.pipeline_pumps:
        pipelines[pl] = PipelineState(topo.nodes[pl]["max_flow_bbl_hr"], init.get("pipelines", {}).get(pl, 1.0))
    for tr in topo.treatments:
        treatment[tr] = TreatmentState(topo.nodes[tr]["max_intake_bbl_hr"], init.get("treatment", {}).get(tr, 1.0))
    return SimState(
        t_min=0, tanks=tanks, pumps=pumps, sources=sources, pipelines=pipelines, treatment=treatment,
        interlocks={t: InterlockState() for t in topo.tanks}, faults=scripted_faults,
        trip_counts={t: 0 for t in topo.tanks}, overflow_bbl={t: 0.0 for t in topo.tanks},
        overflow_events={t: 0 for t in topo.tanks},
    )


def _equipment_pass(s: SimState, eff, topo: Topology, events: list) -> SimState:
    """Phase 1b: fault-driven equipment states, lockouts, start completion, curtailment ramp."""
    t = s.t_min
    pumps, sources = dict(s.pumps), dict(s.sources)
    for f in s.faults:
        if f.start_min == t and not f.announced:
            events.append(Event(t, FAULT, "FAULT_ACTIVE", f.target, {"type": f.type}))
        elif f.end_min == t:
            events.append(Event(t, FAULT, "FAULT_ENDED", f.target, {"type": f.type}))
    for p, ps in s.pumps.items():
        new = ps
        tank_ll = s.interlocks[topo.pumps[p].tank].ll_tripped
        if p in eff.pump_trip:
            new = replace(ps, run_state=TRIPPED, start_ready_at_min=None, auto_started=False)
        elif ps.run_state == TRIPPED and not tank_ll:  # trip cleared -> stopped, available to restart
            new = replace(ps, run_state=STOPPED)
        if not eff.pump_available[p] and new.run_state in (RUNNING, STARTING):  # lockout stops the pump
            new = replace(new, run_state=STOPPED, start_ready_at_min=None, auto_started=False)
        if new.run_state == STARTING and new.start_ready_at_min is not None and t >= new.start_ready_at_min:
            new = replace(new, run_state=RUNNING, start_ready_at_min=None)
            events.append(Event(t, AUTO, "PUMP_RUNNING", p))
        if new is not ps:
            pumps[p] = new
    for sid, src in s.sources.items():
        if src.curtailment_pct != src.curtail_target_pct:
            d = src.curtail_target_pct - src.curtailment_pct
            step_ = src.curtail_rate_pct_per_min
            new_c = src.curtail_target_pct if abs(d) <= step_ else src.curtailment_pct + step_ * (1 if d > 0 else -1)
            sources[sid] = replace(src, curtailment_pct=new_c)
    return replace(s, pumps=pumps, sources=sources)


def _sensor_pass(s: SimState, eff, topo: Topology, cfg: Config, rng) -> SimState:
    """Phase 2: reported levels. Redundant pair -> HIGH reading for high protection, LOW for low protection."""
    lim, noise = cfg.limits, cfg.sensors.noise_bbl
    tanks = {}
    for tid, ts in s.tanks.items():
        v = ts.volume_bbl
        readings = {"A": v, "B": v} if topo.tanks[tid].redundant else {"A": v}
        if noise > 0 and rng is not None:
            readings = {k: x + float(rng.normal(0, noise)) for k, x in readings.items()}
        tf = eff.sensor_faults.get(tid, {})
        readings = {k: faults.sensor_reading(x, tf.get(k), s.t_min) for k, x in readings.items()}
        valid = [x for x in readings.values() if x is not None]
        hi, lo = (max(valid), min(valid)) if valid else (lim.HH, lim.LL)  # no valid signal -> fail-safe
        tanks[tid] = TankState(v, readings, hi, lo)
    return replace(s, tanks=tanks)


def step(state: SimState, topo: Topology, cfg: Config, rng: np.random.Generator | None = None, *,
         inflow_multiplier: float = 1.0, outflow_multiplier: float = 1.0, with_alarms: bool = True) -> SimState:
    """One tick (dt_min). Order: pending actions/faults -> sensors -> interlock -> control -> flow -> integrate -> alarms."""
    t = state.t_min
    dt_h = cfg.time.dt_min / 60.0
    events: list[Event] = []

    # 1. scheduled fault injections + pending action effects that are due
    eff = faults.effective(state, topo)
    s = state
    due = [p for p in s.pending_actions if p.effective_at_min <= t]
    if due:
        for p in due:
            s, ev = actions.apply_effect(s, p, topo, cfg)
            events += ev
        s = replace(s, pending_actions=tuple(p for p in s.pending_actions if p.effective_at_min > t))
    s = _equipment_pass(s, eff, topo, events)
    # 2. sensor model
    s = _sensor_pass(s, eff, topo, cfg, rng)
    # 3. interlock (layer 5): independent of everything below
    if cfg.interlock.enabled:
        s, ev = interlock.interlock_pass(s, topo, cfg)
        events += ev
    # 4. control (layer 2)
    s, ev = control.control_pass(s, eff, topo, cfg)
    events += ev
    # 5. flow allocation
    src_rate = {
        sid: st.rate_bbl_hr * eff.source_mult[sid] * inflow_multiplier * (1 - st.curtailment_pct / 100)
        * (0 if st.shut_in else 1) for sid, st in s.sources.items()
    }
    fr = flow.allocate(
        topo,
        volumes={tid: ts.volume_bbl for tid, ts in s.tanks.items()},
        pump_on={p: ps.run_state == RUNNING and eff.pump_available[p] for p, ps in s.pumps.items()},
        pump_cf=eff.pump_cf,
        pipeline_cap={p: ps.max_flow * eff.pipeline_rf[p] for p, ps in s.pipelines.items()},
        treatment_cap={p: ps.max_intake * eff.treatment_if[p] for p, ps in s.treatment.items()},
        source_rate=src_rate, dt_h=dt_h, outflow_multiplier=outflow_multiplier,
    )
    # 6. integrate, clamp to [0, capacity], record overflow
    tanks, overflow_bbl, overflow_events = {}, dict(s.overflow_bbl), dict(s.overflow_events)
    overflowing = set()
    truck_due = [w for w in s.truck_withdrawals if w[0] == t]
    for tid, ts in s.tanks.items():
        v = ts.volume_bbl + (fr.tank_inflow[tid] - fr.tank_outflow[tid]) * dt_h
        for w in truck_due:
            if w[1] == tid:
                taken = min(w[2], max(v, 0.0))
                v -= taken
                events.append(Event(t, OPERATOR, "TRUCK_LOAD", tid, {"bbl": round(taken, 1)}))
        v = max(v, 0.0)
        cap = topo.tanks[tid].capacity
        if v > cap:
            over = v - cap
            v = cap
            overflow_bbl[tid] += over
            overflowing.add(tid)
            if tid not in s.overflowing:  # log onset only
                overflow_events[tid] += 1
                events.append(Event(t, SYSTEM, "OVERFLOW", tid, {"bbl": round(over, 1)}))
        tanks[tid] = replace(ts, volume_bbl=v)
    curtailed = s.curtailed_bbl + sum(
        st.rate_bbl_hr * eff.source_mult[sid] * inflow_multiplier * st.curtailment_pct / 100 * dt_h
        for sid, st in s.sources.items() if not st.shut_in)
    s = replace(
        s, tanks=tanks, flows=fr, t_min=t + cfg.time.dt_min, overflow_bbl=overflow_bbl,
        overflow_events=overflow_events, overflowing=frozenset(overflowing), curtailed_bbl=curtailed,
        truck_withdrawals=tuple(w for w in s.truck_withdrawals if w[0] > t),
    )
    # 7. alarms (layer 3). Skipped in rollouts: alarms never influence the physics.
    if with_alarms:
        s = replace(s, t_min=t)  # alarms stamped with the tick they describe
        s, ev = alarms.alarm_pass(s, topo, cfg)
        events += ev
        s = replace(s, t_min=t + cfg.time.dt_min)
    return replace(s, new_events=tuple(events))
