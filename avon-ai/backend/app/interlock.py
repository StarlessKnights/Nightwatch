"""Layer 5: independent HH / LL interlock.

Deliberately imports ONLY state/config types. It must never import decision, actions or forecast:
it reads raw (protection-conservative) tank levels and acts, whether or not AVON AI is running.
"""
from __future__ import annotations

from dataclasses import replace

from .models import Config
from .network import Topology
from .state import AUTO, TRIPPED, STOPPED, Event, InterlockState, SimState, RUNNING, STARTING


def interlock_pass(state: SimState, topo: Topology, cfg: Config) -> tuple[SimState, list[Event]]:
    lim, t = cfg.limits, state.t_min
    events: list[Event] = []
    interlocks, sources, pumps = dict(state.interlocks), dict(state.sources), dict(state.pumps)
    trip_counts = dict(state.trip_counts)

    for tank, ts in state.tanks.items():
        il = interlocks[tank]
        hi, lo = ts.reported_bbl, ts.reported_lo_bbl

        # HH: shut in the inflow. Releases only once the level has fallen below the reset threshold.
        tripped = il.tripped
        if not tripped and hi >= lim.HH:
            tripped = True
            trip_counts[tank] = trip_counts.get(tank, 0) + 1
            events.append(Event(t, AUTO, "INTERLOCK_HH_TRIP", tank, {"level": round(hi, 1), "limit": lim.HH}))
        elif tripped and hi < lim.hh_reset_bbl:
            tripped = False
            events.append(Event(t, AUTO, "INTERLOCK_HH_RESET", tank, {"level": round(hi, 1), "reset": lim.hh_reset_bbl}))

        # LL: stop pumps on this tank (dry-run protection). Fail-safe: pump stopped.
        ll = il.ll_tripped
        if not ll and lo <= lim.LL:
            ll = True
            events.append(Event(t, AUTO, "INTERLOCK_LL_TRIP", tank, {"level": round(lo, 1), "limit": lim.LL}))
        elif ll and lo >= lim.ll_reset_bbl:
            ll = False
            events.append(Event(t, AUTO, "INTERLOCK_LL_RESET", tank, {"level": round(lo, 1), "reset": lim.ll_reset_bbl}))

        interlocks[tank] = InterlockState(tripped, ll)
        for s in topo.tank_sources[tank]:
            if sources[s].shut_in != tripped:
                sources[s] = replace(sources[s], shut_in=tripped)
        if ll:
            for p in topo.tank_pumps[tank]:
                if pumps[p].run_state in (RUNNING, STARTING, STOPPED):
                    pumps[p] = replace(pumps[p], run_state=TRIPPED, start_ready_at_min=None, auto_started=False)

    return replace(state, interlocks=interlocks, sources=sources, pumps=pumps, trip_counts=trip_counts), events
