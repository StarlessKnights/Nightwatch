"""Fault catalog, injection, and the *effective* parameter view (base state + active faults)."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .network import Topology
from .state import Fault, SimState

# target_kind + param spec (min/max/default) -- served to the UI so the frontend has no magic numbers.
FAULT_CATALOG = {
    "PUMP_TRIP": {"target_kind": "pump", "params": {}, "handled_by": "Layer 2 auto changeover"},
    "PUMP_DEGRADE": {"target_kind": "pump", "handled_by": "AVON AI (not auto-handled)",
                     "params": {"factor": {"min": 0.1, "max": 0.95, "step": 0.05, "default": 0.45},
                                "ramp_min": {"min": 0, "max": 60, "step": 5, "default": 0}}},
    "PUMP_UNAVAILABLE": {"target_kind": "pump", "params": {}, "handled_by": "Excluded from actions and auto-start"},
    "PIPELINE_RESTRICTION": {"target_kind": "pipeline", "handled_by": "AVON AI",
                             "params": {"factor": {"min": 0.1, "max": 0.95, "step": 0.05, "default": 0.5}}},
    "TREATMENT_CONSTRAINT": {"target_kind": "treatment", "handled_by": "AVON AI",
                             "params": {"factor": {"min": 0.1, "max": 0.95, "step": 0.05, "default": 0.5}}},
    "INFLOW_SURGE": {"target_kind": "source", "handled_by": "AVON AI",
                     "params": {"multiplier": {"min": 1.05, "max": 2.0, "step": 0.05, "default": 1.5}}},
    "LEVEL_SENSOR_FAULT": {"target_kind": "tank", "handled_by": "Sensor trust logic + alarm",
                           "params": {"transmitter": {"options": ["A", "B"], "default": "A"},
                                      "mode": {"options": ["stuck", "drift", "dead"], "default": "stuck"},
                                      "value": {"min": 0, "max": 1000, "step": 10, "default": None},
                                      "rate": {"min": -5, "max": 5, "step": 0.5, "default": -1.0}}},
}


def is_active(f: Fault, t: int) -> bool:
    return f.start_min <= t and (f.end_min is None or t < f.end_min)


@dataclass
class Effective:
    pump_cf: dict
    pump_available: dict
    pump_trip: set
    source_mult: dict
    pipeline_rf: dict
    treatment_if: dict
    sensor_faults: dict  # tank -> {transmitter: Fault}


def effective(state: SimState, topo: Topology) -> Effective:
    t = state.t_min
    eff = Effective(
        pump_cf={p: s.capacity_factor for p, s in state.pumps.items()},
        pump_available={p: s.available for p, s in state.pumps.items()},
        pump_trip=set(),
        source_mult={s: 1.0 for s in state.sources},
        pipeline_rf={p: s.restriction_factor for p, s in state.pipelines.items()},
        treatment_if={p: s.intake_factor for p, s in state.treatment.items()},
        sensor_faults={},
    )
    for f in state.faults:
        if not is_active(f, t):
            continue
        p = f.params
        if f.type == "PUMP_TRIP":
            eff.pump_trip.add(f.target)
        elif f.type == "PUMP_DEGRADE":
            ramp = p.get("ramp_min", 0) or 0
            frac = 1.0 if ramp <= 0 else min(1.0, (t - f.start_min) / ramp)
            eff.pump_cf[f.target] *= 1.0 + (p["factor"] - 1.0) * frac
        elif f.type == "PUMP_UNAVAILABLE":
            eff.pump_available[f.target] = False
        elif f.type == "PIPELINE_RESTRICTION":
            eff.pipeline_rf[f.target] *= p["factor"]
        elif f.type == "TREATMENT_CONSTRAINT":
            eff.treatment_if[f.target] *= p["factor"]
        elif f.type == "INFLOW_SURGE":
            eff.source_mult[f.target] *= p["multiplier"]
        elif f.type == "LEVEL_SENSOR_FAULT":
            eff.sensor_faults.setdefault(f.target, {})[p.get("transmitter", "A")] = f
    return eff


def sensor_reading(true_value: float, f: Fault | None, t: int) -> float | None:
    """Apply a sensor fault to one transmitter. None = dead/bad quality."""
    if f is None:
        return true_value
    mode = f.params.get("mode", "stuck")
    if mode == "dead":
        return None
    if mode == "drift":
        return max(0.0, true_value + f.params.get("rate", -1.0) * (t - f.start_min))
    return float(f.params["value"]) if f.params.get("value") is not None else true_value


def validate(topo: Topology, type_: str, target: str, params: dict) -> dict:
    """Return params merged with catalog defaults; raise ValueError on bad input."""
    spec = FAULT_CATALOG.get(type_)
    if spec is None:
        raise ValueError(f"unknown fault type {type_}")
    if target not in topo.nodes or topo.kind(target) != spec["target_kind"]:
        raise ValueError(f"{type_} needs a {spec['target_kind']} target")
    merged = {k: v.get("default") for k, v in spec["params"].items()}
    merged.update(params or {})
    return merged


def inject(state: SimState, fault: Fault) -> SimState:
    return replace(state, faults=state.faults + (fault,))


def clear(state: SimState, fault_id: str) -> SimState:
    return replace(state, faults=tuple(f for f in state.faults if f.id != fault_id))
