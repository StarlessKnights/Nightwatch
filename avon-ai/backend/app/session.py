"""Thin stateful wrapper around the pure engine. Owns the clock, event log, history, and approvals."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4
import logging

import numpy as np

from . import actions as act
from collections import deque

from . import alarms, consequence, control, decision, diagnosis, faults, messages, pump_model
from .cyber_incident import CyberIncidentManager
from .forecast import rollout, tank_forecasts
from .models import Config, Recommendation, load_config, patch_config
from .network import Topology, impact, load_topology
from .scenarios import list_scenarios, load_scenario
from .sim import step
from .state import ADVISORY, OPERATOR, RUNNING, STOPPED, SYSTEM, TRIPPED, Event, Fault, SimState

DEFAULT_SCENARIO = "scene1_normal"


class Session:
    def __init__(self):
        self.listeners = []
        self.revision = 0
        self.topo: Topology = load_topology()
        self.cfg: Config = load_config()
        self.running = False
        self.speed = 1
        self.engine_enabled = True
        self.scenario_id = DEFAULT_SCENARIO
        self.incident = CyberIncidentManager()
        self.load(DEFAULT_SCENARIO, announce=False)

    # ---------- lifecycle ----------
    def load(self, scenario_id: str, announce: bool = True) -> None:
        state, cfg, meta = load_scenario(scenario_id, self.topo, self.cfg)
        # Ensure sim starts off without pumps activated (STOPPED), available=True, hardware_online=False
        new_pumps = {
            pid: replace(p, run_state=STOPPED, available=True, hardware_online=False)
            for pid, p in state.pumps.items()
        }
        state = replace(state, pumps=new_pumps)
        self.cfg, self.state, self.meta = cfg, state, meta
        self.run_id = uuid4().hex
        self.scenario_id = scenario_id
        self.engine_enabled = meta.get("decision_engine_enabled", True)
        self.rng = np.random.default_rng(meta.get("seed", 0))
        self.running = False
        self.event_log: list[dict] = []
        self.history: list[dict] = []
        self._event_seq = 0
        self._fault_seq = 0
        self.payoff: dict | None = None
        self.ledger = {"shutin": 0.0, "spill": 0.0, "action_fixed": 0.0, "saved": 0.0}
        self.last_advisory: str | None = None
        self.forecast: dict = {}
        self.forecast_do_nothing: dict | None = None
        self._unsent_events: list[dict] = []
        self._unsent_history: list[dict] = []
        self.hardware_nodes: dict[int, dict] = {}
        buf = self.cfg.history.buffer_min
        self.pump_history = {p: deque(maxlen=buf) for p in self.topo.pumps}
        self.tank_history = {t: deque(maxlen=buf) for t in self.topo.tanks}
        self.noise_rng = np.random.default_rng(meta.get("seed", 0) + 1)
        self._record_history()
        self._record_telemetry(0)
        if announce:
            self.log(Event(0, SYSTEM, "SCENARIO_LOADED", None, {"name": meta["name"]}))
        self.refresh_forecast()

    def reset(self) -> None:
        self.incident.reset()
        self.load(self.scenario_id)

    def start_duty_pumps(self) -> None:
        """Starts available duty pumps when the simulation starts."""
        new_pumps = dict(self.state.pumps)
        changed = False
        for pid, p in self.state.pumps.items():
            if p.role == "duty" and p.available and p.run_state == STOPPED:
                new_pumps[pid] = replace(p, run_state=RUNNING)
                changed = True
        if changed:
            self.state = replace(self.state, pumps=new_pumps)
            self._changed()

    def _changed(self) -> None:
        self.revision += 1
        for listener in tuple(self.listeners):
            try:
                listener()
            except Exception:
                logging.getLogger(__name__).exception("Observation listener failed")

    # ---------- events / history ----------
    def log(self, *events: Event) -> None:
        for e in events:
            self._event_seq += 1
            row = {"id": self._event_seq, "t_min": e.t_min, "tag": e.tag, "code": e.code, "asset": e.asset,
                   "params": e.params, "text": messages.render_event(e.code, e.asset, e.params)}
            self.event_log.append(row)
            self._unsent_events.append(row)
        del self.event_log[:-2000]
        if events:
            self._changed()

    def _record_history(self) -> None:
        pt = {"t": self.state.t_min, **{t: round(ts.volume_bbl, 2) for t, ts in self.state.tanks.items()}}
        self.history.append(pt)
        self._unsent_history.append(pt)
        del self.history[:-self.cfg.ui.history_points]

    def _flows(self):
        if self.state.flows is not None:
            return self.state.flows
        return act._alloc(self.state, faults.effective(self.state, self.topo, self.cfg), self.topo, self.cfg, {})

    def _record_telemetry(self, t: int) -> None:
        """Per-pump {Q,P,w,r,s} and per-tank flows into ring buffers (1-minute samples)."""
        fr, h = self._flows(), self.cfg.history
        for p, op in fr.pump_op.items():
            q, pr = op["Q"], op["P"]
            if h.cosmetic_noise and q > 0:  # cosmetic only: never feeds interlock or decision engine
                q = max(q + float(self.noise_rng.normal(0, h.noise_Q_bbl_hr)), 0.0)
                pr = max(pr + float(self.noise_rng.normal(0, h.noise_P)), 0.0)
            rec = {"t_min": t, "Q": round(q, 2), "P": round(pr, 2), "w": round(op["w"], 4), "r": round(op["r"], 3),
                   "s": op["s"], "flow": round(fr.pump_flow[p], 2), "run_state": self.state.pumps[p].run_state}
            self._put(self.pump_history[p], rec)
        for tk, ts in self.state.tanks.items():
            self._put(self.tank_history[tk], {"t_min": t, "volume": round(ts.volume_bbl, 2),
                                              "inflow": round(fr.tank_inflow[tk], 2), "outflow": round(fr.tank_outflow[tk], 2)})

    @staticmethod
    def _put(buf: deque, rec: dict) -> None:
        if buf and buf[-1]["t_min"] == rec["t_min"]:
            buf[-1] = rec
        else:
            buf.append(rec)

    # ---------- stepping ----------
    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            prev = self.state
            self.state = step(prev, self.topo, self.cfg, self.rng)
            self._accrue(prev)
            self.log(*self.state.new_events)
            self._record_history()
            self._record_telemetry(self.state.t_min - self.cfg.time.dt_min)
        self._changed()

    def _accrue(self, prev: SimState) -> None:
        """Realized loss: each interlock shut-in and each overflow event, priced with the consequence model."""
        s, cfg = self.state, self.cfg
        for tank in s.trip_counts:
            rate = sum(prev.sources[x].rate_bbl_hr for x in self.topo.tank_sources[tank])
            self.ledger["shutin"] += (s.trip_counts[tank] - prev.trip_counts[tank]) * consequence.shutin_cost(rate, cfg)
            self.ledger["spill"] += (s.overflow_events[tank] - prev.overflow_events[tank]) * cfg.consequence.spill_penalty

    def ledger_dict(self) -> dict:
        l, c = self.ledger, self.cfg
        curtail = consequence.production_loss(self.state.curtailed_bbl, c)
        loss = l["shutin"] + l["spill"] + l["action_fixed"] + curtail
        return {"loss": round(loss, 2), "saved": round(l["saved"], 2), "net": round(l["saved"] - loss, 2),
                "breakdown": {"shutin": round(l["shutin"], 2), "spill": round(l["spill"], 2),
                              "curtailed_production": round(curtail, 2), "action_fixed": round(l["action_fixed"], 2)}}

    def refresh_forecast(self) -> None:
        """Do-nothing rollout (includes already-approved actions) + NIGHTWATCH predictive alarms."""
        traj = rollout(self.state, self.topo, self.cfg)
        fc = tank_forecasts(traj, self.topo, self.cfg)
        self.forecast = {t: f.model_dump() for t, f in fc.items()}
        self.forecast_as_of_min = traj.start_min
        self.forecast_do_nothing = None
        if self.state.pending_actions:  # also show what would happen WITHOUT the approved actions
            bare = rollout(replace(self.state, pending_actions=()), self.topo, self.cfg)
            self.forecast_do_nothing = {t: f.series for t, f in tank_forecasts(bare, self.topo, self.cfg).items()}
        if self.engine_enabled:
            self.state, ev = alarms.predictive_pass(self.state, self.cfg, {t: f.time_to_HH for t, f in fc.items()})
            self.log(*ev)
        self._changed()

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

    def patch_asset(
        self,
        asset_id: str,
        health: float | None = None,
        available: bool | None = None,
        hardware_online: bool | None = None,
        temperature_c: float | None = None,
        knob_factor: float | None = None,
        hardware_telemetry: dict | None = None,
        run_state: str | None = None,
    ) -> None:

        if asset_id not in self.state.pumps:
            raise KeyError(asset_id)
        ps, change = self.state.pumps[asset_id], []
        if health is not None:
            ps = replace(ps, health=min(max(health, 0.0), 1.0))
            change.append(f"health={ps.health:g}")
        if available is not None:
            ps = replace(ps, available=available)
            change.append(f"available={available}")
            if not available and ps.run_state in ("RUNNING", "STARTING"):
                ps = replace(ps, run_state="STOPPED", start_ready_at_min=None, auto_started=False)
                change.append("run_state=STOPPED")
            elif available and ps.run_state == "STOPPED" and ps.role == "duty":
                ps = replace(ps, run_state="RUNNING")
                change.append("run_state=RUNNING")
        if hardware_online is not None:
            ps = replace(ps, hardware_online=hardware_online)
            change.append(f"hardware_online={hardware_online}")
        if temperature_c is not None:
            ps = replace(ps, temperature_c=round(temperature_c, 1))
            change.append(f"temperature_c={temperature_c}")
        if knob_factor is not None:
            ps = replace(ps, knob_factor=round(knob_factor, 3))
            change.append(f"knob_factor={knob_factor}")
        if hardware_telemetry is not None:
            ps = replace(ps, hardware_telemetry=hardware_telemetry)
        if run_state is not None:
            ps = replace(ps, run_state=run_state)
            change.append(f"run_state={run_state}")

        pumps = dict(self.state.pumps)
        pumps[asset_id] = ps
        self.state = replace(self.state, pumps=pumps)

        eff = faults.effective(self.state, self.topo, self.cfg)
        self.state, ev = control.control_pass(self.state, eff, self.topo, self.cfg)
        if ev:
            self.log(*ev)

        self.log(Event(self.state.t_min, OPERATOR, "ASSET_PATCHED", asset_id, {"change": ", ".join(change)}))
        self.refresh_forecast()

    def update_hardware_node(
        self,
        dev_id: int,
        pump_id: str,
        online: bool,
        knob: float | None = None,
        temperature_c: float | None = None,
        light_level: float | None = None,
        telemetry: dict | None = None
    ) -> dict:
        """Processes real-time hardware status & sensor telemetry from physical Arduinos."""
        if pump_id not in self.state.pumps:
            raise KeyError(pump_id)

        ps = self.state.pumps[pump_id]
        changes = []
        old_online = ps.hardware_online

        # 1. Physical presence / connectivity coupling
        if not online:
            # Arduino disconnected: turn off / lockout
            ps = replace(ps, hardware_online=False, available=False)
            changes.append("available=False")
            if ps.run_state in ("RUNNING", "STARTING"):
                ps = replace(ps, run_state="STOPPED", start_ready_at_min=None, auto_started=False)
                changes.append("run_state=STOPPED")
            if old_online:
                self.log(Event(self.state.t_min, "HARDWARE", "HARDWARE_DISCONNECTED", pump_id, {"dev": dev_id}))
        else:
            # Arduino connected: restore availability (hardware online)
            ps = replace(ps, hardware_online=True, available=True)
            changes.append("available=True")
            # Never automatically turn on backup/standby pumps!
            # Only duty pumps activate when connected
            if ps.role != "standby" and ps.run_state in ("STOPPED", "STARTING"):
                ps = replace(ps, run_state="RUNNING", start_ready_at_min=None)
                changes.append("run_state=RUNNING")
            if not old_online:
                self.log(Event(self.state.t_min, "HARDWARE", "HARDWARE_CONNECTED", pump_id, {"dev": dev_id}))

        # 2. Knob / Health / Throttle input (0.0 to 1.0)
        if knob is not None:
            knob_val = min(max(float(knob), 0.0), 1.0)
            if ps.knob_factor is None or abs(ps.knob_factor - knob_val) >= 0.01:
                ps = replace(ps, knob_factor=round(knob_val, 3), health=round(knob_val, 3))
                changes.append(f"knob={knob_val:.2f}")
                self.log(Event(self.state.t_min, "HARDWARE", "HARDWARE_KNOB_ADJUSTED", pump_id, {"knob": round(knob_val, 3)}))

        # 3. Thermal telemetry & overheat trip protection (85.0 C trip threshold)
        if temperature_c is not None:
            temp_val = round(float(temperature_c), 1)
            ps = replace(ps, temperature_c=temp_val)
            changes.append(f"temp={temp_val}C")
            if temp_val >= 85.0:
                has_overheat = any(
                    f.type == "PUMP_TRIP" and f.target == pump_id and "Thermal overheat" in str(f.params.get("reason", ""))
                    for f in self.state.faults
                )
                if not has_overheat:
                    try:
                        self.inject_fault("PUMP_TRIP", pump_id, {"reason": f"Thermal overheat: {temp_val}C"}, None)
                        ps = replace(ps, run_state="TRIPPED", start_ready_at_min=None, auto_started=False)
                        changes.append("run_state=TRIPPED")
                        self.log(Event(self.state.t_min, "HARDWARE", "THERMAL_TRIP", pump_id, {"temp_c": temp_val}))
                    except Exception:
                        pass
            elif temp_val <= 65.0:
                overheat_faults = [
                    f for f in self.state.faults
                    if f.target == pump_id and "Thermal overheat" in str(f.params.get("reason", ""))
                ]
                for of in overheat_faults:
                    self.clear_fault(of.id)
                if ps.run_state == "TRIPPED":
                    ps = replace(ps, run_state="STOPPED")
                    changes.append("run_state=STOPPED")

        # 4. Telemetry container
        if telemetry or light_level is not None:
            tel = dict(ps.hardware_telemetry or {})
            if light_level is not None:
                tel["light_level"] = round(float(light_level), 1)
            if telemetry:
                tel.update(telemetry)
            ps = replace(ps, hardware_telemetry=tel)

        pumps = dict(self.state.pumps)
        pumps[pump_id] = ps
        self.state = replace(self.state, pumps=pumps)

        self.hardware_nodes[dev_id] = {
            "dev": dev_id,
            "pump": pump_id,
            "online": ps.hardware_online,
            "temperature_c": ps.temperature_c,
            "knob_factor": ps.knob_factor,
            "telemetry": ps.hardware_telemetry,
            "last_seen_min": self.state.t_min
        }

        # Trigger basic control pass (standby auto-start or duty restart)
        eff = faults.effective(self.state, self.topo, self.cfg)
        self.state, ev = control.control_pass(self.state, eff, self.topo, self.cfg)
        if ev:
            self.log(*ev)

        self.refresh_forecast()
        return {
            "pump": pump_id,
            "changes": changes,
            "run_state": ps.run_state,
            "available": ps.available,
            "health": ps.health,
            "temperature_c": ps.temperature_c
        }

    def get_hardware_summary(self) -> dict:
        return {
            "nodes": self.hardware_nodes,
            "active_pumps": {
                p: {
                    "online": ps.hardware_online,
                    "available": ps.available,
                    "run_state": ps.run_state,
                    "temperature_c": ps.temperature_c,
                    "knob_factor": ps.knob_factor,
                    "health": ps.health,
                }
                for p, ps in self.state.pumps.items()
            }
        }
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
        self.ledger["saved"] += self.payoff["savings"]  # projected avoided cost vs do-nothing at approval time
        self.ledger["action_fixed"] += opt.cost_breakdown.fixed
        self.log(Event(self.state.t_min, OPERATOR, "ACTION_APPROVED", None,
                       {"label": opt.label, "lead_min": opt.lead_time_min, "option": option_id}))
        self.last_advisory = None
        self.refresh_forecast()
        return rec

    def commit_verified_actions(self, combo, option, expected_revision: int) -> None:
        """Operator-only commit after deterministic evaluation of this exact revision."""
        if not self.engine_enabled:
            raise PermissionError("decision engine disabled")
        if self.revision != expected_revision:
            raise ValueError("State changed during validation; retry approval or pause playback")
        act.validate_combo(combo, self.topo)
        if not option.feasible or option.action_id != act.combo_id(combo):
            raise ValueError("Action was not validated")
        for a in combo:
            self.state = act.schedule(self.state, a, self.cfg)
        self.log(Event(self.state.t_min, OPERATOR, "ACTION_APPROVED", None,
                       {"label": option.label, "lead_min": option.lead_time_min, "option": option.action_id}))
        self.refresh_forecast()

    # ---------- serialization ----------
    def state_dict(self) -> dict:
        s, topo = self.state, self.topo
        eff = faults.effective(s, topo, self.cfg)
        fr = self._flows()
        fstat = {t: f["status"] for t, f in self.forecast.items()}
        rate = {sid: st.rate_bbl_hr * eff.source_mult[sid] * (1 - st.curtailment_pct / 100) * (1 - st.shed_pct / 100)
                for sid, st in s.sources.items()}
        return {
            "run_id": self.run_id, "revision": self.revision,
            "t_min": s.t_min, "clock": messages.fmt_clock(s.t_min, self.cfg.ui.start_clock),
            "tanks": {t: {
                "volume": round(ts.volume_bbl, 2), "capacity": topo.tanks[t].capacity, "reported": round(ts.reported_bbl, 2),
                "sensors": ts.level_sensors, "status": fstat.get(t, "normal"), "role": topo.tanks[t].role,
                "inflow": round(fr.tank_inflow[t], 2), "outflow": round(fr.tank_outflow[t], 2),
                "overflow_bbl": round(s.overflow_bbl[t], 2), "interlock": {"tripped": s.interlocks[t].tripped, "ll_tripped": s.interlocks[t].ll_tripped},
                "trips": s.trip_counts[t]} for t, ts in s.tanks.items()},
            "pumps": {p: {
                "role": ps.role, "run_state": ps.run_state, "health": ps.health, "eff_health": round(eff.pump_w[p], 4),
                "eff_capacity_factor": round(eff.pump_cf[p], 3), "available": eff.pump_available[p],
                "flow": round(fr.pump_flow[p], 2), "limited_by": fr.pump_limited_by[p], "auto_started": ps.auto_started,
                "tank": topo.pumps[p].tank, "pipeline": topo.pumps[p].pipeline,
                "Q": round(fr.pump_op[p]["Q"], 2), "P": round(fr.pump_op[p]["P"], 2), "r": round(fr.pump_op[p]["r"], 3),
                "diagnosis": self._diagnosis(p),
                "hardware_online": ps.hardware_online,
                "temperature_c": ps.temperature_c,
                "knob_factor": ps.knob_factor,
                "hardware_telemetry": ps.hardware_telemetry} for p, ps in s.pumps.items()},
            "sources": {sid: {"rate": st.rate_bbl_hr, "eff_rate": round(st.rate_bbl_hr * eff.source_mult[sid], 2),
                              "flow": round(rate[sid], 2), "curtailment_pct": round(st.curtailment_pct, 1),
                              "curtail_target_pct": st.curtail_target_pct, "shut_in": st.shut_in, "shed_pct": round(st.shed_pct, 1)} for sid, st in s.sources.items()},
            "pipelines": {pl: {"flow": round(fr.pipeline_flow[pl], 2), "max_flow": ps.max_flow,
                               "r": round(eff.pipeline_r[pl], 3),
                               "cap": round(fr.pipeline_cap[pl], 1)} for pl, ps in s.pipelines.items()},
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
            "hardware": self.get_hardware_summary(),
            "airgap_engaged": self.incident.airgap_engaged,
        }

    def _envelope(self) -> dict:
        return {
            "running": self.running, "speed": self.speed, "engine_enabled": self.engine_enabled,
            "scenario": {"id": self.scenario_id, "name": self.meta["name"], "description": self.meta["description"]},
            "auto_changeover_on_low_flow": self.cfg.control.auto_changeover_on_low_flow,
            "state": self.state_dict(),
            "forecast": {"tanks": self.forecast, "do_nothing": self.forecast_do_nothing,
                         "series_step_min": self.cfg.time.forecast_series_step_min, "as_of_min": self.forecast_as_of_min},
            "payoff": self.payoff, "ledger": self.ledger_dict(),
            "incident": self.incident.get_status(),
        }

    def tick_message(self) -> dict:
        msg = {"type": "tick", **self._envelope(), "new_events": self._unsent_events, "history": self._unsent_history}
        self._unsent_events, self._unsent_history = [], []
        return msg

    def snapshot(self) -> dict:
        """Full state without consuming the pending tick deltas."""
        return {"type": "sync", **self._envelope(), "event_log": self.event_log, "history": self.history}

    def sync_message(self) -> dict:
        return self.snapshot()

    # ---------- pump detail ----------
    def _diagnosis(self, pump_id: str) -> dict:
        d = diagnosis.diagnose(list(self.pump_history[pump_id]), self.cfg)
        return {**d, "text": messages.diagnosis_text(d["code"], d["w_est"], d["r_est"])}

    def diagnosis(self, asset_id: str) -> dict:
        if asset_id not in self.topo.pumps:
            raise KeyError(asset_id)
        return self._diagnosis(asset_id)

    def _asset_events(self, asset_id: str, since: int) -> list[dict]:
        topo = self.topo
        related = {asset_id}
        if asset_id in topo.pumps:
            related |= {topo.pumps[asset_id].pipeline, topo.pumps[asset_id].tank}
        else:
            related |= set(topo.tank_sources[asset_id]) | set(topo.tank_pumps[asset_id])
        kinds = {"FAULT_ACTIVE": "fault", "FAULT_INJECTED": "fault", "FAULT_CLEARED": "fault", "FAULT_ENDED": "fault",
                 "STANDBY_AUTOSTART": "auto", "STANDBY_AUTOSTOP": "auto", "DUTY_AUTORESTART": "auto",
                 "INTERLOCK_HH_TRIP": "trip", "INTERLOCK_LL_TRIP": "trip", "ACTION_APPROVED": "approval",
                 "ACTION_EFFECTIVE": "approval", "ALARM_RAISED": "alarm"}
        out, seen = [], set()
        for e in self.event_log:
            kind = kinds.get(e["code"])
            if kind is None or e["t_min"] < since:
                continue
            if e["code"] == "ALARM_RAISED" and e["asset"] != asset_id:
                continue
            if e["code"] not in ("ACTION_APPROVED",) and e["asset"] not in related:
                continue
            if e["code"] in ("FAULT_ACTIVE", "FAULT_INJECTED") and e["params"].get("type") == "PUMP_TRIP":
                kind = "trip"
            key = (e["t_min"], e["code"], e["asset"])
            if key not in seen:
                seen.add(key)
                out.append({"t": e["t_min"], "kind": kind, "label": e["text"]})
        return out

    def asset_history(self, asset_id: str, window_min: int) -> dict:
        now = self.state.t_min
        since = now - window_min
        if asset_id in self.pump_history:
            allrecs = list(self.pump_history[asset_id])
            recs = [(i, r) for i, r in enumerate(allrecs) if r["t_min"] >= since]
            pm = self.cfg.pump_model
            series = {"t": [], "Q": [], "P": [], "w_est": [], "r_est": [], "flow": []}
            expected = []
            for i, r in recs:
                d = diagnosis.diagnose(allrecs[:i + 1], self.cfg)
                series["t"].append(r["t_min"]); series["Q"].append(r["Q"]); series["P"].append(r["P"])
                series["w_est"].append(d["w_est"]); series["r_est"].append(d["r_est"]); series["flow"].append(r["flow"])
                expected.append(round(pump_model.operating_point(1.0, r["s"], r["r"], pm)[0], 2))
            return {"kind": "pump", "series": series, "events": self._asset_events(asset_id, since), "expected_flow": expected}
        if asset_id in self.tank_history:
            recs = [r for r in self.tank_history[asset_id] if r["t_min"] >= since]
            series = {k: [r[k] if k != "t_min" else r[k] for r in recs] for k in ("t_min", "volume", "inflow", "outflow")}
            series["t"] = series.pop("t_min")
            return {"kind": "tank", "series": series, "events": self._asset_events(asset_id, since), "expected_flow": []}
        raise KeyError(asset_id)

    def asset_curves(self, asset_id: str, points: int = 40) -> dict:
        if asset_id not in self.topo.pumps:
            raise KeyError(asset_id)
        info = self.topo.pumps[asset_id]
        eff = faults.effective(self.state, self.topo, self.cfg)
        pm, w, r = self.cfg.pump_model, eff.pump_w[asset_id], eff.pipeline_r[info.pipeline]
        s = 1.0  # curves are drawn for the pump at speed even when it is a stopped standby
        qs = [pm.Qmax * i / (points - 1) for i in range(points)]
        pt = lambda f: [{"Q": round(q, 1), "H": round(max(f(q), 0.0), 2)} for q in qs]  # noqa: E731
        q_op, h_op = pump_model.operating_point(w, s, r, pm)
        q_h, h_h = pump_model.operating_point(1.0, s, 1.0, pm)
        return {
            "pump_curve": pt(lambda q: pump_model.pump_head(q, w, s, pm)),
            "pump_curve_healthy": pt(lambda q: pump_model.pump_head(q, 1.0, s, pm)),
            "system_curve": pt(lambda q: pump_model.system_head(q, r, pm)),
            "system_curve_healthy": pt(lambda q: pump_model.system_head(q, 1.0, pm)),
            "operating_point": {"Q": round(q_op, 2), "H": round(h_op, 2)},
            "healthy_point": {"Q": round(q_h, 2), "H": round(h_h, 2)},
            "running": self.state.pumps[asset_id].run_state == "RUNNING", "w": round(w, 4), "r": round(r, 3),
        }

    def impact(self, asset_id: str) -> dict:
        if asset_id not in self.topo.nodes:
            raise KeyError(asset_id)
        out = dict(impact(self.topo, asset_id))
        tths = {t: f["time_to_HH"] for t, f in self.forecast.items() if f["time_to_HH"] is not None}
        out["first_to_limit"] = min(tths, key=tths.get) if tths else None
        return out
