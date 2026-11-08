"""Pump curve meets system curve (pure, closed form). Illustrative synthetic parameters in config.json.

  a = H0 / Qmax^2
  pump:   H = w * (H0 * s^2 - a * Q^2)
  system: H = Hs + k * r * Q^2
"""
from __future__ import annotations

from math import sqrt

from .models import PumpModelCfg


def _a(pm: PumpModelCfg) -> float:
    return pm.H0 / pm.Qmax ** 2


def operating_point(w: float, s: float, r: float, pm: PumpModelCfg) -> tuple[float, float]:
    """(Q kW, P head) where the pump curve meets the system curve. Dead-head -> (0, 0)."""
    if s <= 0 or w <= 0:
        return 0.0, 0.0
    num = w * pm.H0 * s * s - pm.Hs
    if num <= 0:
        return 0.0, 0.0
    q = sqrt(num / (w * _a(pm) + pm.k * r))
    return q, pm.Hs + pm.k * r * q * q


def pump_head(q: float, w: float, s: float, pm: PumpModelCfg) -> float:
    return w * (pm.H0 * s * s - _a(pm) * q * q)


def system_head(q: float, r: float, pm: PumpModelCfg) -> float:
    return pm.Hs + pm.k * r * q * q


def healthy_flow(pm: PumpModelCfg) -> float:
    return operating_point(1.0, 1.0, 1.0, pm)[0]


def capacity_factor(w: float, s: float, r: float, pm: PumpModelCfg) -> float:
    """Derived display value: Q(w,s,r) / Q(1,1,1)."""
    return operating_point(w, s, r, pm)[0] / healthy_flow(pm)


def pipeline_flow_limit(r: float, pm: PumpModelCfg) -> float:
    """Most a pipeline with restriction r can pass even with every pump at shut-off head (H0).
    Stands in for a parallel-pump solver: a second pump behind a blocked line adds almost nothing."""
    return sqrt(max(pm.H0 - pm.Hs, 0.0) / (pm.k * max(r, 1e-9)))
