"""Thin stateful wrapper around the pure engine. Owns the clock, event log, history, and approvals."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import actions as act
from . import alarms, decision, faults, messages
from .forecast import rollout, tank_forecasts
from .models import Config, Recommendation, load_config, patch_config
from .network import Topology, impact, load_topology
from .scenarios import list_scenarios, load_scenario
from .sim import step
from .state import ADVISORY, OPERATOR, SYSTEM, Event, Fault, SimState

DEFAULT_SCENARIO = "scene1_normal"


class Session:
    def __init__(self):
        self.topo: Topology = load_topology()
        self.cfg: Config = load_config()
        self.running = False
        self.speed = 1
        self.engine_enabled = True
        self.scenario_id = DEFAULT_SCENARIO
        self.load(DEFAULT_SCENARIO, announce=False)

    # ---------- lifecycle ----------
    def load(self, scenario_id: str, announce: bool = True) -> None:
        state, cfg, meta = load_scenario(scenario_id, self.topo, self.cfg)
        self.cfg, self.state, self.meta = cfg, state, meta
        self.scenario_id = scenario_id
        self.engine_enabled = meta.get("decision_engine_enabled", True)
        self.rng = np.random.default_rng(meta.get("seed", 0))
        self.running = False
        self.event_log: list[dict] = []
        self.history: list[dict] = []
        self._event_seq = 0
        self._fault_seq = 0
        self.payoff: dict | None = None
        self.last_advisory: str | None = None
        self.forecast: dict = {}
        self.forecast_do_nothing: dict | None = None
        self._unsent_events: list[dict] = []
        self._unsent_history: list[dict] = []
        self._record_history()
        if announce:
            self.log(Event(0, SYSTEM, "SCENARIO_LOADED", None, {"name": meta["name"]}))
        self.refresh_forecast()

    def reset(self) -> None:
        self.load(self.scenario_id)

    # ---------- events / history ----------
    def log(self, *events: Event) -> None:
        for e in events:
            self._event_seq += 1
            row = {"id": self._event_seq, "t_min": e.t_min, "tag": e.tag, "code": e.code, "asset": e.asset,
                   "params": e.params, "text": messages.render_event(e.code, e.asset, e.params)}
            self.event_log.append(row)
            self._unsent_events.append(row)
        del self.event_log[:-2000]

    def _record_history(self) -> None:
        pt = {"t": self.state.t_min, **{t: round(ts.volume_bbl, 2) for t, ts in self.state.tanks.items()}}
        self.history.append(pt)
        self._unsent_history.append(pt)
        del self.history[:-self.cfg.ui.history_points]

    # ---------- stepping ----------
    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            self.state = step(self.state, self.topo, self.cfg, self.rng)
            self.log(*self.state.new_events)
            self._record_history()

    def refresh_forecast(self) -> None:
        """Do-nothing rollout (includes already-approved actions) + AVON AI predictive alarms."""
        traj = rollout(self.state, self.topo, self.cfg)
        fc = tank_forecasts(traj, self.topo, self.cfg)
        self.forecast = {t: f.model_dump() for t, f in fc.items()}
        self.forecast_do_nothing = None
        if self.state.pending_actions:  # also show what would happen WITHOUT the approved actions
            bare = rollout(replace(self.state, pending_actions=()), self.topo, self.cfg)
            self.forecast_do_nothing = {t: f.series for t, f in tank_forecasts(bare, self.topo, self.cfg).items()}
        if self.engine_enabled:
            self.state, ev = alarms.predictive_pass(self.state, self.cfg, {t: f.time_to_HH for t, f in fc.items()})
            self.log(*ev)

    # ---------- commands ----------
    def inject_fault(self, type_: str, target: str, params: dict, end_min: int | None) -> Fault:
        merged = faults.validate(self.topo, type_, target, params)
        if type_ == "LEVEL_SENSOR_FAULT" and merged.get("mode") == "stuck" and merged.get("value") is None:
            merged["value"] = self.state.tanks[target].level_sensors.get(merged["transmitter"]) or 0.0
        self._fault_seq += 1
        f = Fault(f"F-{self._fault_seq:03d}", type_, target, merged, self.state.t_min, end_min, announced=True)
        self.state = faults.inject(self.state, f)
        self.log(Event(self.state.t_min, "FAULT", "FAULT_INJECTED", target, {"type": type_}))
        self.refresh_forecast()
        return f

    def clear_fault(self, fault_id: str) -> None:
        f = next((x for x in self.state.faults if x.id == fault_id), None)
        if f is None:
            raise KeyError(fault_id)
        self.state = faults.clear(self.state, fault_id)
        self.log(Event(self.state.t_min, "FAULT", "FAULT_CLEARED", f.target, {"type": f.type}))
        self.refresh_forecast()

    def patch_asset(self, asset_id: str, capacity_factor: float | None, available: bool | None) -> None:
        if asset_id not in self.state.pumps:
            raise KeyError(asset_id)
        ps, change = self.state.pumps[asset_id], []
        if capacity_factor is not None:
            ps = replace(ps, capacity_factor=min(max(capacity_factor, 0.0), 1.0))
            change.append(f"capacity_factor={ps.capacity_factor:g}")
        if available is not None:
            ps = replace(ps, available=available)
            change.append(f"available={available}")
        pumps = dict(self.state.pumps)
        pumps[asset_id] = ps
        self.state = replace(self.state, pumps=pumps)
        self.log(Event(self.state.t_min, OPERATOR, "ASSET_PATCHED", asset_id, {"change": ", ".join(change)}))
        self.refresh_forecast()

    def patch_config(self, patch: dict) -> None:
        self.cfg = patch_config(self.cfg, patch)
        self.log(Event(self.state.t_min, OPERATOR, "CONFIG_CHANGED", None, {"change": str(patch)}))
        self.refresh_forecast()

    def set_engine(self, enabled: bool) -> None:
        self.engine_enabled = enabled
        self.log(Event(self.state.t_min, SYSTEM, "ENGINE_TOGGLED", None, {"state": "enabled" if enabled else "DISABLED"}))
        if not enabled:  # drop predictive alarms
            self.state = replace(self.state, alarms=tuple(a for a in self.state.alarms if a.kind != "PREDICTIVE"))
        self.refresh_forecast()

    def ack(self, alarm_id: str) -> None:
        self.state, ev = alarms.acknowledge(self.state, alarm_id)
        self.log(*ev)

    # ---------- advisory ----------
    def recommendation(self) -> Recommendation:
        return decision.recommend(self.state, self.topo, self.cfg, engine_enabled=self.engine_enabled)

    def note_advisory(self, rec: Recommendation) -> None:
        """Log a new ADVISORY event when the best option changes (audit trail)."""
        best = rec.best_option_id
        if not self.engine_enabled or best in (None, act.DO_NOTHING):
            self.last_advisory = None
            return
        if best != self.last_advisory:
            self.last_advisory = best
            label = next(o.label for o in rec.options if o.action_id == best)
            self.log(Event(self.state.t_min, ADVISORY, "RECOMMENDATION", None, {"label": label, "headline": rec.headline, "option": best}))

    def approve(self, option_id: str) -> Recommendation:
        """Approval is the ONLY way advisory actions affect the sim."""
        if not self.engine_enabled:
            raise PermissionError("decision engine disabled")
        rec = self.recommendation()
        opt = next((o for o in rec.options if o.action_id == option_id), None)
        if opt is None or option_id == act.DO_NOTHING:
            raise KeyError(option_id)
        if not opt.feasible:
            raise ValueError("option is not feasible: " + ",".join(opt.reason_codes))
        combo = act.combo_from_id(option_id)
        for a in combo:
            self.state = act.schedule(self.state, a, self.cfg)
        self.payoff = {"option_id": option_id, "label": opt.label, "approved_min": self.state.t_min,
                       "do_nothing_cost": rec.do_nothing_cost, "action_cost": opt.cost_breakdown.total,
                       "savings": round(rec.do_nothing_cost - (opt.cost_breakdown.total or 0), 2)}
        self.log(Event(self.state.t_min, OPERATOR, "ACTION_APPROVED", None,
                       {"label": opt.label, "lead_min": opt.lead_time_min, "option": option_id}))
        self.last_advisory = None
        self.refresh_forecast()
        return rec

    # ---------- serialization ----------
    def state_dict(self) -> dict:
        s, topo = self.state, self.topo
        eff = faults.effective(s, topo)
        fr = s.flows or act._alloc(s, eff, topo, self.cfg.time.dt_min / 60, {})
        fstat = {t: f["status"] for t, f in self.forecast.items()}
        rate = {sid: st.rate_bbl_hr * eff.source_mult[sid] * (1 - st.curtailment_pct / 100) * (0 if st.shut_in else 1)
                for sid, st in s.sources.items()}
        return {
            "t_min": s.t_min, "clock": messages.fmt_clock(s.t_min, self.cfg.ui.start_clock),
            "tanks": {t: {
                "volume": round(ts.volume_bbl, 2), "capacity": topo.tanks[t].capacity, "reported": round(ts.reported_bbl, 2),
                "sensors": ts.level_sensors, "status": fstat.get(t, "normal"), "role": topo.tanks[t].role,
                "inflow": round(fr.tank_inflow[t], 2), "outflow": round(fr.tank_outflow[t], 2),
                "overflow_bbl": round(s.overflow_bbl[t], 2), "interlock": {"tripped": s.interlocks[t].tripped, "ll_tripped": s.interlocks[t].ll_tripped},
                "trips": s.trip_counts[t]} for t, ts in s.tanks.items()},
            "pumps": {p: {
                "role": ps.role, "run_state": ps.run_state, "capacity_factor": ps.capacity_factor,
                "eff_capacity_factor": round(eff.pump_cf[p], 3), "available": eff.pump_available[p],
                "flow": round(fr.pump_flow[p], 2), "limited_by": fr.pump_limited_by[p], "auto_started": ps.auto_started,
                "tank": topo.pumps[p].tank, "pipeline": topo.pumps[p].pipeline} for p, ps in s.pumps.items()},
            "sources": {sid: {"rate": st.rate_bbl_hr, "eff_rate": round(st.rate_bbl_hr * eff.source_mult[sid], 2),
                              "flow": round(rate[sid], 2), "curtailment_pct": round(st.curtailment_pct, 1),
                              "curtail_target_pct": st.curtail_target_pct, "shut_in": st.shut_in} for sid, st in s.sources.items()},
            "pipelines": {pl: {"flow": round(fr.pipeline_flow[pl], 2), "max_flow": ps.max_flow,
                               "restriction_factor": round(eff.pipeline_rf[pl], 3),
                               "cap": round(ps.max_flow * eff.pipeline_rf[pl], 1)} for pl, ps in s.pipelines.items()},
            "treatment": {tr: {"flow": round(fr.treatment_flow[tr], 2), "max_intake": ts.max_intake,
                               "intake_factor": round(eff.treatment_if[tr], 3),
                               "cap": round(ts.max_intake * eff.treatment_if[tr], 1)} for tr, ts in s.treatment.items()},
            "faults": [{"id": f.id, "type": f.type, "target": f.target, "params": f.params, "start_min": f.start_min,
                        "end_min": f.end_min, "active": faults.is_active(f, s.t_min)} for f in s.faults],
            "alarms": [{"id": a.id, "tag": a.tag, "condition": a.condition, "priority": a.priority, "kind": a.kind,
                        "state": a.state, "raised_min": a.raised_min, "cleared_min": a.cleared_min, "value": a.value,
                        "text": messages.render_event("ALARM_RAISED", a.tag, {"condition": a.condition, "priority": a.priority})}
                       for a in s.alarms],
            "pending_actions": [{"id": p.id, "kind": p.kind, "effective_at_min": p.effective_at_min, "label": act.from_id(p.id).label}
                                for p in s.pending_actions],
            "truck_withdrawals": len(s.truck_withdrawals),
        }

    def _envelope(self) -> dict:
        return {
            "running": self.running, "speed": self.speed, "engine_enabled": self.engine_enabled,
            "scenario": {"id": self.scenario_id, "name": self.meta["name"], "description": self.meta["description"]},
            "auto_changeover_on_low_flow": self.cfg.control.auto_changeover_on_low_flow,
            "state": self.state_dict(),
            "forecast": {"tanks": self.forecast, "do_nothing": self.forecast_do_nothing,
                         "series_step_min": self.cfg.time.forecast_series_step_min, "as_of_min": self.state.t_min},
            "payoff": self.payoff,
        }

    def tick_message(self) -> dict:
        msg = {"type": "tick", **self._envelope(), "new_events": self._unsent_events, "history": self._unsent_history}
        self._unsent_events, self._unsent_history = [], []
        return msg

    def snapshot(self) -> dict:
        """Full state without consuming the pending tick deltas."""
        return {"type": "sync", **self._envelope(), "event_log": self.event_log, "history": self.history}

    def sync_message(self) -> dict:
        self._unsent_events, self._unsent_history = [], []
        return self.snapshot()

    def impact(self, asset_id: str) -> dict:
        if asset_id not in self.topo.nodes:
            raise KeyError(asset_id)
        out = dict(impact(self.topo, asset_id))
        tths = {t: f["time_to_HH"] for t, f in self.forecast.items() if f["time_to_HH"] is not None}
        out["first_to_limit"] = min(tths, key=tths.get) if tths else None
        return out
