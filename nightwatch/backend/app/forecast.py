"""Forecast: rollout of the same step() with no UI. The do-nothing rollout IS the time-to-limit forecast."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import actions as act
from .models import Config, TankForecast
from .network import Topology
from .sim import step
from .state import SimState


@dataclass
class Trajectory:
    start_min: int
    volumes: dict  # tank -> [volume at t0, t0+1, ...]
    final: SimState
    trips: dict
    overflow_events: dict
    overflow_bbl: dict
    curtailed_bbl: float
    events: list = field(default_factory=list)


def rollout(state: SimState, topo: Topology, cfg: Config, actions: list | tuple = (), horizon_min: int | None = None,
            rng: np.random.Generator | None = None, *, inflow_multiplier: float = 1.0,
            outflow_multiplier: float = 1.0, with_alarms: bool = False) -> Trajectory:
    """Run step() forward. `actions` are scheduled as if approved right now (approval buffer applies)."""
    # TODO(phase3): Monte Carlo / sensitivity wrap this via inflow_multiplier, outflow_multiplier and rng.
    h = cfg.time.horizon_min if horizon_min is None else horizon_min
    # A forecast must not peek at faults that have not happened yet (scripted scenario faults).
    s = replace(state, faults=tuple(f for f in state.faults if f.start_min <= state.t_min))
    for a in actions:
        s = act.schedule(s, a, cfg)
    vols = {t: [ts.volume_bbl] for t, ts in s.tanks.items()}
    events: list = []
    steps = h // cfg.time.dt_min
    for _ in range(steps):
        s = step(s, topo, cfg, rng, inflow_multiplier=inflow_multiplier, outflow_multiplier=outflow_multiplier,
                 with_alarms=with_alarms)
        for t, ts in s.tanks.items():
            vols[t].append(ts.volume_bbl)
        if s.new_events:
            events += s.new_events
    return Trajectory(
        state.t_min, vols, s,
        trips={t: s.trip_counts[t] - state.trip_counts[t] for t in s.trip_counts},
        overflow_events={t: s.overflow_events[t] - state.overflow_events[t] for t in s.overflow_events},
        overflow_bbl={t: s.overflow_bbl[t] - state.overflow_bbl[t] for t in s.overflow_bbl},
        curtailed_bbl=s.curtailed_bbl - state.curtailed_bbl, events=events,
    )


def closed_form_time_to_limit(volume: float, limit: float, inflow: float, outflow: float) -> float | None:
    """Constant-rate estimate in minutes (kWh, kW). Used as a regression check against rollout()."""
    if volume >= limit:
        return 0.0
    net = inflow - outflow
    return None if net <= 0 else (limit - volume) / net * 60.0


def first_crossing(series: list[float], threshold: float, dt_min: float = 1.0) -> float | None:
    """Minutes until the series first reaches threshold (linear interpolation); 0 if already there."""
    if series[0] >= threshold:
        return 0.0
    for k in range(1, len(series)):
        if series[k] >= threshold:
            a, b = series[k - 1], series[k]
            return ((k - 1) + (threshold - a) / (b - a)) * dt_min
    return None


def status_for(tth_h: float | None, tth_hh: float | None, overflow: float | None, cfg: Config) -> str:
    st = cfg.status
    if tth_hh is not None and tth_hh <= st.critical_min or overflow is not None:
        return "critical"
    if tth_hh is not None and tth_hh <= st.warning_min:
        return "warning"
    if tth_hh is not None or tth_h is not None:
        return "watch"
    return "normal"


def tank_forecasts(traj: Trajectory, topo: Topology, cfg: Config) -> dict[str, TankForecast]:
    lim, dt = cfg.limits, cfg.time.dt_min
    step_n = max(cfg.time.forecast_series_step_min // dt, 1)
    out = {}
    for tank, series in traj.volumes.items():
        h = first_crossing(series, lim.H, dt)
        hh = first_crossing(series, lim.HH, dt)
        of = first_crossing(series, topo.tanks[tank].capacity, dt) if max(series) >= topo.tanks[tank].capacity else None
        out[tank] = TankForecast(
            tank=tank, time_to_H=_r(h), time_to_HH=_r(hh), time_to_overflow=_r(of),
            status=status_for(h, hh, of, cfg), series=[round(v, 1) for v in series[::step_n]])
    return out


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 2)
