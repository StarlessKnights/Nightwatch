"""Layer 2: basic control. Automatic changeover of standby on duty trip; duty auto-restart."""
from __future__ import annotations

from dataclasses import replace

from .faults import Effective
from .models import Config
from .network import Topology
from .state import AUTO, RUNNING, STARTING, STOPPED, TRIPPED, Event, SimState


def control_pass(state: SimState, eff: Effective, topo: Topology, cfg: Config) -> tuple[SimState, list[Event]]:
    c, t = cfg.control, state.t_min
    pumps, events = dict(state.pumps), []

    for duty_id, info in topo.pumps.items():
        if info.role != "duty":
            continue
        ps = pumps[duty_id]
        ll = state.interlocks[info.tank].ll_tripped  # low-level protection: starting more pumps would not help
        unavailable = not eff.pump_available[duty_id]
        tripped = ps.run_state == TRIPPED and not ll
        degraded = eff.pump_cf[duty_id] < c.low_flow_pct / 100.0
        low = ps.run_state == RUNNING and degraded
        ticks = ps.low_flow_ticks + 1 if low else 0
        if ticks != ps.low_flow_ticks:
            ps = pumps[duty_id] = replace(ps, low_flow_ticks=ticks)

        reason = ("trip" if tripped else "unavailable" if unavailable
                  else "low_flow" if c.auto_changeover_on_low_flow and ticks >= c.low_flow_duration_min else None)
        healthy = ps.run_state == RUNNING and not degraded

        for sb in topo.standbys_of.get(duty_id, ()):
            sps = pumps[sb]
            if reason and not ll and sps.run_state == STOPPED and eff.pump_available[sb]:
                pumps[sb] = replace(sps, run_state=STARTING, start_ready_at_min=t + c.standby_start_delay_min, auto_started=True)
                events.append(Event(t, AUTO, "STANDBY_AUTOSTART", sb, {"duty": duty_id, "reason": reason, "delay_min": c.standby_start_delay_min}))
            elif c.auto_stop_standby and sps.auto_started and sps.run_state in (RUNNING, STARTING) and healthy:
                pumps[sb] = replace(sps, run_state=STOPPED, start_ready_at_min=None, auto_started=False)
                events.append(Event(t, AUTO, "STANDBY_AUTOSTOP", sb, {"duty": duty_id}))

        # Duty came back (fault cleared / lockout lifted) and is idle: restart it.
        if ps.run_state == STOPPED and not unavailable and not ll and duty_id not in eff.pump_trip:
            pumps[duty_id] = replace(ps, run_state=STARTING, start_ready_at_min=t + c.standby_start_delay_min)
            events.append(Event(t, AUTO, "DUTY_AUTORESTART", duty_id, {"delay_min": c.standby_start_delay_min}))

    # TODO(phase3): lead/lag rotation after N hours of runtime (stretch goal)
    return replace(state, pumps=pumps), events
