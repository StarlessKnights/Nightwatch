"""Action library: definitions, lead times, preconditions, effects, costs. Pure."""
from __future__ import annotations

from dataclasses import dataclass, replace

from . import flow, faults
from .faults import Effective
from .models import Config
from .network import Topology
from .state import OPERATOR, STARTING, STOPPED, Event, PendingAction, SimState

START_STANDBY_PUMP = "START_STANDBY_PUMP"
REDUCE_PRODUCTION = "REDUCE_PRODUCTION"
DISPATCH_TRUCK = "DISPATCH_TRUCK"
DO_NOTHING = "DO_NOTHING"


@dataclass(frozen=True, eq=False)
class Action:
    kind: str
    params: dict

    @property
    def id(self) -> str:
        if self.kind == START_STANDBY_PUMP:
            return f"{self.kind}:{self.params['pump']}"
        if self.kind == REDUCE_PRODUCTION:
            return f"{self.kind}:{self.params['source']}:{self.params['pct']}"
        return f"{self.kind}:{self.params['tank']}"

    @property
    def label(self) -> str:
        if self.kind == START_STANDBY_PUMP:
            return f"Start standby chiller pump {self.params['pump']}"
        if self.kind == REDUCE_PRODUCTION:
            return f"Migrate {self.params['pct']}% of {self.params['source']} workloads away"
        return f"Deploy portable chiller to {self.params['tank']}"


def from_id(action_id: str) -> Action:
    kind, *rest = action_id.split(":")
    if kind == START_STANDBY_PUMP:
        return Action(kind, {"pump": rest[0]})
    if kind == REDUCE_PRODUCTION:
        return Action(kind, {"source": rest[0], "pct": int(rest[1])})
    if kind == DISPATCH_TRUCK:
        return Action(kind, {"tank": rest[0]})
    raise ValueError(f"unknown action {action_id}")


def combo_id(actions: list[Action]) -> str:
    return "+".join(a.id for a in actions)


def combo_from_id(option_id: str) -> list[Action]:
    return [from_id(p) for p in option_id.split("+")]


def validate_combo(combo: list[Action], topo: Topology) -> None:
    """Validate external proposals before any dictionary lookup or rollout."""
    if not 1 <= len(combo) <= 4:
        raise ValueError("Provide between one and four actions")
    for a in combo:
        if a.kind == START_STANDBY_PUMP:
            if set(a.params) != {"pump"} or a.params["pump"] not in topo.pumps:
                raise ValueError("Unknown pump or invalid parameters")
            if topo.pumps[a.params["pump"]].role != "standby":
                raise ValueError("Only standby pumps can be proposed")
        elif a.kind == REDUCE_PRODUCTION:
            if set(a.params) != {"source", "pct"} or a.params["source"] not in topo.sources:
                raise ValueError("Unknown source or invalid parameters")
            if type(a.params["pct"]) is not int or not 1 <= a.params["pct"] <= 100:
                raise ValueError("Load reduction must be an integer from 1 to 100")
        elif a.kind == DISPATCH_TRUCK:
            if set(a.params) != {"tank"} or a.params["tank"] not in topo.tanks:
                raise ValueError("Unknown tank or invalid parameters")
        else:
            raise ValueError("Unsupported action")
    if any(conflicts(a, b) for i, a in enumerate(combo) for b in combo[i + 1:]):
        raise ValueError("Conflicting or duplicate actions")


def lead_time_min(a: Action, cfg: Config) -> float:
    """Intrinsic lead time (time from taking effect to delivering effect). Approval buffer is added separately."""
    if a.kind == START_STANDBY_PUMP:
        return cfg.control.standby_start_delay_min
    if a.kind == REDUCE_PRODUCTION:
        return cfg.actions.REDUCE_PRODUCTION["ramp_min"]
    return cfg.actions.DISPATCH_TRUCK["lead_time_min"]


def lead_total_min(a: Action, cfg: Config) -> float:
    return lead_time_min(a, cfg) + cfg.decision.operator_approval_buffer_min


def target_tanks(a: Action, topo: Topology) -> list[str]:
    if a.kind == START_STANDBY_PUMP:
        return [topo.pumps[a.params["pump"]].tank]
    if a.kind == REDUCE_PRODUCTION:
        return [topo.sources[a.params["source"]]]
    return [a.params["tank"]]


def active_window_min(a: Action, cfg: Config) -> float | None:
    """Minutes after approval until the action stops acting; None = lasts the whole horizon."""
    if a.kind == DISPATCH_TRUCK:
        d = cfg.actions.DISPATCH_TRUCK
        return cfg.decision.operator_approval_buffer_min + d["lead_time_min"] + (d["max_loads"] - 1) * d["cycle_min"]
    return None


def _trucks_in_use(state: SimState) -> int:
    in_flight = {w[3] for w in state.truck_withdrawals}
    return len(in_flight) + sum(1 for p in state.pending_actions if p.kind == DISPATCH_TRUCK)


def preconditions(a: Action, state: SimState, eff: Effective, topo: Topology, cfg: Config,
                  extra_trucks: int = 0) -> list[str]:
    """Hard-constraint reason codes (empty = OK)."""
    if any(conflicts(a, from_id(p.id)) for p in state.pending_actions):
        return ["PRECONDITION_FAILED"]
    if a.kind == START_STANDBY_PUMP:
        p = a.params["pump"]
        if not eff.pump_available[p]:
            return ["ASSET_UNAVAILABLE"]
        if p in eff.pump_trip:
            return ["ASSET_TRIPPED"]
        if eff.pump_w[p] < 0.5:
            return ["ASSET_DEGRADED"]
        if state.pumps[p].run_state != STOPPED:
            return ["PRECONDITION_FAILED"]
        # Would starting it actually move more water, or is the path already the limit?
        base = _alloc(state, eff, topo, cfg, {})
        more = _alloc(state, eff, topo, cfg, {p: True})
        tank = topo.pumps[p].tank
        if more.tank_outflow[tank] - base.tank_outflow[tank] < 1.0:
            lim = more.pump_limited_by[p]
            return ["TREATMENT_CAP_EXCEEDED" if lim == "treatment" else "PIPELINE_CAP_EXCEEDED"]
        return []
    if a.kind == REDUCE_PRODUCTION:
        s = state.sources[a.params["source"]]
        return ["PRECONDITION_FAILED"] if s.curtail_target_pct >= a.params["pct"] else []
    if _trucks_in_use(state) + extra_trucks >= cfg.actions.DISPATCH_TRUCK["fleet"]:
        return ["PRECONDITION_FAILED"]
    return []


def _alloc(state, eff, topo, cfg, force_on: dict):
    return flow.allocate(
        topo,
        volumes={t: s.volume_bbl for t, s in state.tanks.items()},
        pump_on={p: (force_on.get(p, s.run_state == "RUNNING") and eff.pump_available[p]) for p, s in state.pumps.items()},
        pump_w=eff.pump_w, pump_model_cfg=cfg.pump_model,
        pipeline_cap={p: s.max_flow for p, s in state.pipelines.items()}, pipeline_r=eff.pipeline_r,
        treatment_cap={p: s.max_intake * eff.treatment_if[p] for p, s in state.treatment.items()},
        source_rate={s: st.rate_bbl_hr * eff.source_mult[s] * (1 - st.curtailment_pct / 100) * (1 - st.shed_pct / 100)
                     for s, st in state.sources.items()},
        dt_h=cfg.time.dt_min / 60,
    )


def cost_parts(a: Action, cfg: Config, horizon_min: float) -> tuple[float, float]:
    """(fixed, hourly_total) for an action running to the end of the horizon (or its max window)."""
    if a.kind == START_STANDBY_PUMP:
        c = cfg.actions.START_STANDBY_PUMP
        hours = max(horizon_min - cfg.decision.operator_approval_buffer_min, 0) / 60
        return c["fixed_cost"], c["hourly_cost"] * hours
    if a.kind == DISPATCH_TRUCK:
        d = cfg.actions.DISPATCH_TRUCK
        first = lead_total_min(a, cfg)
        loads = sum(1 for k in range(d["max_loads"]) if first + k * d["cycle_min"] <= horizon_min)
        return d["fixed_cost"] + d["cost_per_load"] * loads, 0.0
    return 0.0, 0.0  # curtailment cost is the derived production loss


def generate(state: SimState, topo: Topology, cfg: Config, at_risk: set) -> list[Action]:
    """Single actions aimed at tanks that are at risk."""
    out: list[Action] = []
    for p, info in topo.pumps.items():
        if info.role == "standby" and info.tank in at_risk:
            out.append(Action(START_STANDBY_PUMP, {"pump": p}))
    for s, tank in topo.sources.items():
        if tank in at_risk:
            for pct in cfg.decision.curtailment_options_pct:
                out.append(Action(REDUCE_PRODUCTION, {"source": s, "pct": pct}))
    for tank in sorted(at_risk):
        out.append(Action(DISPATCH_TRUCK, {"tank": tank}))
    return out


def conflicts(a: Action, b: Action) -> bool:
    """Pairs that make no sense together (same lever twice)."""
    if a.kind != b.kind:
        return False
    key = {START_STANDBY_PUMP: "pump", REDUCE_PRODUCTION: "source", DISPATCH_TRUCK: "tank"}[a.kind]
    return a.params[key] == b.params[key]


def schedule(state: SimState, a: Action, cfg: Config, approved_min: int | None = None) -> SimState:
    """Approval is the ONLY way an advisory action reaches the sim: it lands in pending_actions."""
    t = state.t_min if approved_min is None else approved_min
    pa = PendingAction(a.id, a.kind, dict(a.params), t + cfg.decision.operator_approval_buffer_min, t)
    return replace(state, pending_actions=state.pending_actions + (pa,))


def apply_effect(state: SimState, pa: PendingAction, topo: Topology, cfg: Config) -> tuple[SimState, list[Event]]:
    t, a = state.t_min, from_id(pa.id)
    ev = lambda code, **kw: Event(t, OPERATOR, code, kw.pop("asset", None), kw)  # noqa: E731
    if pa.kind == START_STANDBY_PUMP:
        p = pa.params["pump"]
        ps = state.pumps[p]
        eff = faults.effective(state, topo, cfg)
        if ps.run_state != STOPPED or not eff.pump_available[p] or p in eff.pump_trip or eff.pump_w[p] < 0.5:
            return state, [ev("ACTION_SKIPPED", label=a.label, why="pump not startable", asset=p)]
        d = cfg.control.standby_start_delay_min
        pumps = dict(state.pumps)
        pumps[p] = replace(ps, run_state=STARTING, start_ready_at_min=t + d, auto_started=False)
        return replace(state, pumps=pumps), [ev("ACTION_EFFECTIVE", label=a.label, asset=p)]
    if pa.kind == REDUCE_PRODUCTION:
        s = pa.params["source"]
        ramp = cfg.actions.REDUCE_PRODUCTION["ramp_min"]
        src = dict(state.sources)
        pct = float(pa.params["pct"])
        src[s] = replace(src[s], curtail_target_pct=pct, curtail_rate_pct_per_min=pct / max(ramp, 1))
        return replace(state, sources=src), [ev("ACTION_EFFECTIVE", label=a.label, asset=s)]
    d = cfg.actions.DISPATCH_TRUCK
    tank = pa.params["tank"]
    loads = tuple((t + d["lead_time_min"] + k * d["cycle_min"], tank, d["load_bbl"], state.next_dispatch_id)
                  for k in range(d["max_loads"]))
    return (replace(state, truck_withdrawals=state.truck_withdrawals + loads, next_dispatch_id=state.next_dispatch_id + 1),
            [ev("ACTION_EFFECTIVE", label=a.label, asset=tank)])
