"""Decision engine: generate -> filter -> simulate -> rank. Stateless: recommend(snapshot, config, overrides)."""
from __future__ import annotations

from dataclasses import replace

from . import actions as act
from . import consequence, diagnosis, faults, messages
from .forecast import Trajectory, first_crossing, rollout, tank_forecasts
from .models import (Affected, Cause, Config, CostBreakdown, Diagnosis, Option, Reason, Recommendation)
from .network import Topology, impact
from .state import SimState

HARD = {"ASSET_UNAVAILABLE", "PRECONDITION_FAILED", "LEAD_TIME_EXCEEDS_DEADLINE", "PIPELINE_CAP_EXCEEDED",
        "TREATMENT_CAP_EXCEEDED"}


def _reasons(codes: list[str]) -> list[Reason]:
    return [Reason(code=c, text=messages.reason_text(c)) for c in codes]


def _nominal_rates(state: SimState, eff, topo: Topology) -> dict:
    return {t: sum(state.sources[s].rate_bbl_hr * eff.source_mult[s] for s in ss) for t, ss in topo.tank_sources.items()}


def _peak_margin(traj: Trajectory, cfg: Config) -> float:
    return cfg.limits.HH - max(max(v) for v in traj.volumes.values())


def _summary(traj: Trajectory, cfg: Config) -> dict:
    n = max(cfg.time.forecast_series_step_min // cfg.time.dt_min, 1)
    return {t: {"peak_bbl": round(max(v), 1), "final_bbl": round(v[-1], 1),
                "time_to_HH": _r(first_crossing(v, cfg.limits.HH, cfg.time.dt_min)),
                "series": [round(x, 1) for x in v[::n]]} for t, v in traj.volumes.items()}


def _r(x):
    return None if x is None else round(x, 2)


def pump_diagnoses(state: SimState, eff, topo: Topology, cfg: Config) -> dict:
    out = {}
    for p, ps in state.pumps.items():
        if ps.run_state != "RUNNING" or not eff.pump_available[p]:
            continue
        d = diagnosis.diagnose_instant(eff.pump_w[p], 1.0, eff.pipeline_r[topo.pumps[p].pipeline], cfg)
        out[p] = Diagnosis(**d)
    return out


def probable_cause(state: SimState, eff, topo: Topology, cfg: Config, diag: dict) -> list[Cause]:
    """Evidence fields from the pump diagnosis (w_est / r_est) and effective readings, not prose."""
    out = []
    for p, ps in state.pumps.items():
        if ps.run_state == "TRIPPED":
            out.append(Cause(asset=p, evidence_field="run_state", value="TRIPPED"))
        if not eff.pump_available[p]:
            out.append(Cause(asset=p, evidence_field="available", value=False))
        d = diag.get(p)
        if d and d.code not in ("NONE", "FLOW_TOO_LOW"):
            out.append(Cause(asset=p, evidence_field="diagnosis", value=d.code))
            if d.code in ("PUMP_WEAR", "COMPOUND"):
                out.append(Cause(asset=p, evidence_field="w_est", value=d.w_est))
    for pl, v in eff.pipeline_r.items():
        if v > 1.0:
            out.append(Cause(asset=pl, evidence_field="restriction_r", value=round(v, 2)))
    for p, v in eff.treatment_if.items():
        if v < 1.0:
            out.append(Cause(asset=p, evidence_field="intake_factor", value=round(v, 2)))
    for s, v in eff.source_mult.items():
        if v > 1.0:
            out.append(Cause(asset=s, evidence_field="rate_multiplier", value=round(v, 2)))
    for tank, ts in state.tanks.items():
        a, b = ts.level_sensors.get("A"), ts.level_sensors.get("B")
        if topo.tanks[tank].redundant and (a is None or b is None or abs(a - b) > cfg.sensors.disagree_tolerance_bbl):
            out.append(Cause(asset=tank, evidence_field="level_sensor_disagreement", value=None if a is None or b is None else round(abs(a - b), 1)))
    return out


def recommend(state: SimState, topo: Topology, cfg: Config, unavailable_overrides: frozenset | set = frozenset(),
              engine_enabled: bool = True) -> Recommendation:
    # TODO(phase3): the LLM layer reads this Recommendation object (and nothing else).
    if unavailable_overrides:
        state = replace(state, pumps={p: (replace(s, available=False) if p in unavailable_overrides else s)
                                      for p, s in state.pumps.items()})
    eff = faults.effective(state, topo, cfg)
    t0 = state.t_min
    horizon = cfg.time.horizon_min
    buffer = cfg.decision.operator_approval_buffer_min
    start_clock = cfg.ui.start_clock

    base = rollout(state, topo, cfg)
    fc = tank_forecasts(base, topo, cfg)
    rates = _nominal_rates(state, eff, topo)
    base_consequence = consequence.trajectory_consequence(base.trips, base.overflow_events, rates, cfg)
    do_nothing_cost = round(base_consequence, 2)
    base_margin = _peak_margin(base, cfg)
    base_breach = any(base.trips.values()) or any(base.overflow_events.values())

    at_risk = {t for t, f in fc.items() if f.status != "normal"}
    diag = pump_diagnoses(state, eff, topo, cfg)
    cause = probable_cause(state, eff, topo, cfg, diag)
    faulted = [c.asset for c in cause]
    up, down = [], []
    for a in faulted:
        for x in impact(topo, a)["upstream"]:
            if x not in up and x not in faulted:
                up.append(x)
        for x in impact(topo, a)["downstream"]:
            if x not in down and x not in faulted:
                down.append(x)
    first = min((t for t in fc if fc[t].time_to_HH is not None), key=lambda t: fc[t].time_to_HH, default=None)
    status = max((f.status for f in fc.values()), key=["normal", "watch", "warning", "critical"].index, default="normal")

    dn_reasons = ["STILL_REACHES_HH"] if base_breach else (["INSUFFICIENT_MARGIN"] if base_margin < cfg.decision.min_margin_bbl and at_risk else [])
    dn_feasible = not dn_reasons
    dn_opt = Option(
        action_id=act.DO_NOTHING, label="Do nothing", feasible=dn_feasible, reason_codes=dn_reasons,
        reasons=_reasons(dn_reasons),
        cost_breakdown=CostBreakdown(fixed=0, hourly=0, production_loss=0, expected_consequence=do_nothing_cost, total=do_nothing_cost),
        margin_bbl=round(base_margin, 1), act_by_min=None, act_by_clock=None, lead_time_min=0, trajectory_summary=_summary(base, cfg))
    options: list[Option] = [dn_opt]

    def evaluate(combo: list[act.Action]) -> tuple[Option, Trajectory | None]:
        fixed = hourly = 0.0
        for a in combo:
            f_, h_ = act.cost_parts(a, cfg, horizon)
            fixed += f_
            hourly += h_
        lead = max(act.lead_total_min(a, cfg) for a in combo)
        # --- hard constraints (no simulation needed) ---
        codes: list[str] = []
        extra_trucks = 0
        for a in combo:
            codes += act.preconditions(a, state, eff, topo, cfg, extra_trucks)
            if a.kind == act.DISPATCH_TRUCK:
                extra_trucks += 1
        deadlines = []
        for a in combo:
            for tank in act.target_tanks(a, topo):
                tth = fc[tank].time_to_HH
                if tth is not None:
                    deadlines.append(tth - act.lead_total_min(a, cfg))
                    if act.lead_total_min(a, cfg) > tth:
                        codes.append("LEAD_TIME_EXCEEDS_DEADLINE")
        act_by = t0 + min(deadlines) if deadlines else None
        codes = list(dict.fromkeys(codes))
        label = " + ".join(a.label for a in combo)
        oid = act.combo_id(combo)
        if codes:
            return Option(
                action_id=oid, label=label, feasible=False, reason_codes=codes, reasons=_reasons(codes),
                cost_breakdown=CostBreakdown(fixed=round(fixed, 2), hourly=round(hourly, 2), production_loss=0,
                                             expected_consequence=0, total=None),
                margin_bbl=None, act_by_min=act_by, act_by_clock=None if act_by is None else messages.fmt_clock(act_by, start_clock),
                lead_time_min=lead, trajectory_summary=None), None
        # --- simulate the whole horizon ---
        traj = rollout(state, topo, cfg, combo)
        margin = _peak_margin(traj, cfg)
        breach = any(traj.trips.values()) or any(traj.overflow_events.values())
        codes = []
        if breach:
            windows = [w for w in (act.active_window_min(a, cfg) for a in combo) if w is not None]
            first_breach = min((first_crossing(v, cfg.limits.HH, cfg.time.dt_min) or horizon) for v in traj.volumes.values())
            codes.append("DURATION_NOT_SUSTAINABLE" if windows and first_breach > min(windows) else "STILL_REACHES_HH")
        elif margin < cfg.decision.min_margin_bbl:
            codes.append("INSUFFICIENT_MARGIN")
        targets = {t for a in combo for t in act.target_tanks(a, topo)}
        for tank, v in traj.volumes.items():
            if tank in targets:
                continue
            b, o = fc[tank].time_to_HH, first_crossing(v, cfg.limits.HH, cfg.time.dt_min)
            if o is not None and (b is None or o < b - 1.0):
                codes.append("MOVES_PROBLEM_DOWNSTREAM")
                break
        prod = consequence.production_loss(traj.curtailed_bbl, cfg)
        cons = consequence.trajectory_consequence(traj.trips, traj.overflow_events, rates, cfg)
        total = fixed + hourly + prod + cons
        return Option(
            action_id=oid, label=label, feasible=not codes, reason_codes=codes, reasons=_reasons(codes),
            cost_breakdown=CostBreakdown(fixed=round(fixed, 2), hourly=round(hourly, 2), production_loss=round(prod, 2),
                                         expected_consequence=round(cons, 2), total=round(total, 2)),
            margin_bbl=round(margin, 1), act_by_min=act_by,
            act_by_clock=None if act_by is None else messages.fmt_clock(act_by, start_clock),
            lead_time_min=lead, trajectory_summary=_summary(traj, cfg)), traj

    if engine_enabled and at_risk:
        singles = act.generate(state, topo, cfg, at_risk)
        evaluated = [(a, evaluate([a])[0]) for a in singles]
        options += [o for _, o in evaluated]
        # Pairs only from singles that failed on the simulation (hard failures can't be rescued; feasible
        # singles dominate any pair containing them on cost).
        cand = [a for a, o in evaluated if not o.feasible and not (set(o.reason_codes) & HARD)]
        pairs = [[a, b] for i, a in enumerate(cand) for b in cand[i + 1:] if not act.conflicts(a, b)]
        for combo in pairs[:cfg.decision.max_pair_options]:
            options.append(evaluate(combo)[0])

    # --- rank feasible options (excluding the reference row) by total cost, then margin, then act-by ---
    pool = [o for o in options if o.feasible and o.action_id != act.DO_NOTHING]
    pool.sort(key=lambda o: (o.cost_breakdown.total, -(o.margin_bbl or 0), o.act_by_min if o.act_by_min is not None else 1e9, o.action_id))
    ranked = [o.action_id for o in pool]
    best = pool[0] if pool else None
    if not at_risk and dn_feasible:
        best_id = act.DO_NOTHING
    else:
        best_id = best.action_id if best else None
    savings = round(do_nothing_cost - best.cost_breakdown.total, 2) if best else 0.0
    # order: ranked feasible, then DO_NOTHING reference, then rejected (cheapest first)
    rest = sorted([o for o in options if o not in pool and o.action_id != act.DO_NOTHING],
                  key=lambda o: (o.cost_breakdown.total is None, o.cost_breakdown.total or 0, o.action_id))
    ordered = pool + [dn_opt] + rest

    if not engine_enabled:
        hl_code, hl = "ENGINE_OFF", messages.headline("ENGINE_OFF")
    elif not at_risk:
        hl_code, hl = "NO_RISK", messages.headline("NO_RISK", horizon_h=horizon // 60)
    else:
        tank = first or max(at_risk, key=lambda t: fc[t].series[-1])
        tth = fc[tank].time_to_HH
        if tth is None:
            hl_code, hl = "WATCH", messages.headline("WATCH", tank=tank)
        elif tth <= 0:
            hl_code, hl = "ALREADY_HH", messages.headline("ALREADY_HH", tank=tank)
        elif best is None:
            hl_code, hl = "NO_FEASIBLE", messages.headline("NO_FEASIBLE", tank=tank, minutes=round(tth, 1))
        elif best.act_by_clock is None:
            hl_code, hl = "REACHES_HH_NO_DEADLINE", messages.headline("REACHES_HH_NO_DEADLINE", tank=tank, minutes=round(tth, 1))
        else:
            hl_code, hl = "REACHES_HH", messages.headline("REACHES_HH", tank=tank, minutes=round(tth, 1), act_by=best.act_by_clock)

    return Recommendation(
        as_of_min=t0, headline=hl, headline_code=hl_code, status=status, forecast=fc, probable_cause=cause, diagnosis=diag,
        affected_assets=Affected(upstream=up, downstream=down, first_to_limit=first), options=ordered,
        ranked_option_ids=ranked, best_option_id=best_id, do_nothing_cost=do_nothing_cost, savings=savings,
        engine_enabled=engine_enabled)
