"""Layer 3: alarm engine (ISA-18.2 inspired, simplified). Deadband + on-delay, one alarm per tag+condition."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .models import Config
from .network import Topology
from .state import (ACTIVE_ACK, ACTIVE_UNACK, ADVISORY, ALARM, CLEARED, OPERATOR, RUNNING, STARTING,
                    TRIPPED, Alarm, Event, SimState)

CLEARED_KEEP_MIN = 30


@dataclass
class Cond:
    tag: str
    condition: str
    priority: int
    kind: str
    trigger: bool
    clear: bool
    value: float | None = None
    on_delay: int | None = None  # None -> config default


def _key(tag: str, cond: str) -> str:
    return f"{tag}:{cond}"


def level_conditions(state: SimState, topo: Topology, cfg: Config) -> list[Cond]:
    lim, db = cfg.limits, cfg.limits.deadband_bbl
    out = []
    for tank, ts in state.tanks.items():
        hi, lo = ts.reported_bbl, ts.reported_lo_bbl
        out += [
            Cond(tank, "HH", 1, "PROCESS", hi >= lim.HH, hi < lim.HH - db, hi),
            Cond(tank, "H", 2, "PROCESS", hi >= lim.H, hi < lim.H - db, hi),
            Cond(tank, "L", 3, "PROCESS", lo <= lim.L, lo > lim.L + db, lo),
            Cond(tank, "LL", 1, "PROCESS", lo <= lim.LL, lo > lim.LL + db, lo),
        ]
        il = state.interlocks[tank]
        out.append(Cond(tank, "INTERLOCK_HH", 1, "SYSTEM", il.tripped, not il.tripped, hi, on_delay=0))
        if topo.tanks[tank].redundant:
            a, b = ts.level_sensors.get("A"), ts.level_sensors.get("B")
            bad = a is None or b is None
            diff = abs(a - b) if not bad else None
            tol = cfg.sensors.disagree_tolerance_bbl
            out.append(Cond(tank, "SENSOR_DISAGREE", 3, "SYSTEM", bad or diff > tol,
                            (not bad) and diff < tol - db, diff, on_delay=0))
    return out


def equipment_conditions(state: SimState, topo: Topology) -> list[Cond]:
    out = []
    for p, ps in state.pumps.items():
        out.append(Cond(p, "PUMP_TRIP", 2, "SYSTEM", ps.run_state == TRIPPED, ps.run_state != TRIPPED, on_delay=0))
        if ps.role == "standby":
            on = ps.auto_started and ps.run_state in (STARTING, RUNNING)
            out.append(Cond(p, "STANDBY_AUTOSTART", 3, "SYSTEM", on, not on, on_delay=0))
    return out


def _update(existing: tuple, conds: list[Cond], timers: dict, t: int, default_delay: int, event_tag: str,
            managed) -> tuple[tuple, dict, list[Event]]:
    """Advance alarms managed by this pass (`managed(alarm)` selects them) through their state machine."""
    by_id = {a.id: a for a in existing if managed(a)}
    others = [a for a in existing if not managed(a)]
    timers, events = dict(timers), []
    for c in conds:
        k = _key(c.tag, c.condition)
        a = by_id.get(k)
        active = a is not None and a.state != CLEARED
        timers[k] = timers.get(k, 0) + 1 if c.trigger else 0
        delay = default_delay if c.on_delay is None else c.on_delay
        if not active and c.trigger and timers[k] >= max(delay, 1 if delay == 0 else delay):
            by_id[k] = Alarm(k, c.tag, c.condition, c.priority, c.kind, ACTIVE_UNACK, t, None, c.value)
            events.append(Event(t, event_tag, "ALARM_RAISED", c.tag, {"condition": c.condition, "priority": c.priority, "value": c.value}))
        elif active and c.clear:  # clearing needs the deadband crossed
            by_id[k] = replace(a, state=CLEARED, cleared_min=t, value=c.value)
            events.append(Event(t, event_tag, "ALARM_CLEARED", c.tag, {"condition": c.condition}))
        elif active:
            by_id[k] = replace(a, value=c.value)
    kept = [a for a in by_id.values() if a.state != CLEARED or t - (a.cleared_min or t) <= CLEARED_KEEP_MIN]
    return tuple(others + kept), timers, events


def alarm_pass(state: SimState, topo: Topology, cfg: Config) -> tuple[SimState, list[Event]]:
    conds = level_conditions(state, topo, cfg) + equipment_conditions(state, topo)
    alarms, timers, events = _update(state.alarms, conds, state.alarm_timers, state.t_min,
                                     cfg.limits.on_delay_min, ALARM, lambda a: a.kind != "PREDICTIVE")
    return replace(state, alarms=alarms, alarm_timers=timers), events


def predictive_pass(state: SimState, cfg: Config, time_to_hh: dict) -> tuple[SimState, list[Event]]:
    """NIGHTWATCH predictive alarm: forecast time-to-HH below threshold. Applied by the session, not step()."""
    st = cfg.status
    conds = []
    for tank, tth in time_to_hh.items():
        trig = tth is not None and tth < st.predictive_alarm_min
        clr = tth is None or tth > st.predictive_alarm_min + st.predictive_deadband_min
        conds.append(Cond(tank, "FORECAST_HH", 2, "PREDICTIVE", trig, clr, tth, on_delay=0))
    alarms, timers, events = _update(state.alarms, conds, state.alarm_timers, state.t_min, 0, ADVISORY,
                                     lambda a: a.kind == "PREDICTIVE")
    return replace(state, alarms=alarms, alarm_timers=timers), events


def acknowledge(state: SimState, alarm_id: str) -> tuple[SimState, list[Event]]:
    alarms, events = [], []
    for a in state.alarms:
        if a.id == alarm_id and a.state == ACTIVE_UNACK:
            a = replace(a, state=ACTIVE_ACK)
            events.append(Event(state.t_min, OPERATOR, "ALARM_ACK", a.tag, {"condition": a.condition}))
        alarms.append(a)
    return replace(state, alarms=tuple(alarms)), events
