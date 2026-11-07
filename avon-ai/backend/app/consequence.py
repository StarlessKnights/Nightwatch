"""Derived consequence model. All numbers from config (illustrative)."""
from __future__ import annotations

from .models import Config
from .network import Topology


def shutin_cost(inflow_rate_bbl_hr: float, cfg: Config) -> float:
    c = cfg.consequence
    return inflow_rate_bbl_hr * c.shutin_duration_h * c.production_value_per_bbl + c.restart_cost


def overflow_cost(inflow_rate_bbl_hr: float, cfg: Config) -> float:
    """Overflow is the worst outcome: a shut-in PLUS a spill penalty."""
    return shutin_cost(inflow_rate_bbl_hr, cfg) + cfg.consequence.spill_penalty


def production_loss(curtailed_bbl: float, cfg: Config) -> float:
    return curtailed_bbl * cfg.consequence.production_value_per_bbl


def trajectory_consequence(trips: dict, overflows: dict, tank_rates: dict, cfg: Config) -> float:
    """Expected consequence of a rollout. `trips`/`overflows` are event counts per tank;
    `tank_rates` the nominal inflow (bbl/hr) feeding each tank. Deterministic, so expected == actual."""
    total = 0.0
    for tank, n in trips.items():
        total += n * shutin_cost(tank_rates.get(tank, 0.0), cfg)
    for tank, n in overflows.items():
        total += n * overflow_cost(tank_rates.get(tank, 0.0), cfg)
    return total
