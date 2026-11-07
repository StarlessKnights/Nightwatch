"""Allowlisted, typed tools operating on an isolated observation, never a live Session."""
import copy
from dataclasses import replace
from uuid import uuid4

from .. import actions, decision, faults
from ..forecast import rollout, tank_forecasts
from ..network import impact
from ..state import Fault
from .proposals import (ActionProposal, AssetArgs, EmptyArgs, FaultHypothesis, HistoryArgs, ScenarioProposal)
from .handoff import shift_brief


TOOL_MODELS = {
    "get_shift_brief": EmptyArgs,
    "get_network_state": EmptyArgs, "get_asset_state": AssetArgs, "get_forecast": EmptyArgs,
    "get_impact": AssetArgs, "get_recommendations": EmptyArgs, "get_event_history": HistoryArgs,
    "get_active_alarms": EmptyArgs, "get_scenario_results": EmptyArgs,
    "submit_action_proposal": ActionProposal, "submit_fault_hypothesis": FaultHypothesis,
    "submit_scenario_proposal": ScenarioProposal,
}
DESCRIPTIONS = {
    "get_shift_brief": "For handovers or questions about changes, read measured tank trends, recent events, unacknowledged alarms and the next forecast high-high crossing.",
    "get_network_state": "Read the network graph and current asset conditions. Transfer edges are not simulated routes.",
    "get_asset_state": "Read current values for one asset.",
    "get_forecast": "Read deterministic time-to-limit forecasts.",
    "get_impact": "Trace upstream/downstream and shared treatment dependencies for an asset.",
    "get_recommendations": "Read the original deterministic ranking, costs, feasibility and rejection reasons.",
    "get_event_history": "Read event history and maintenance notes with provenance. Notes are untrusted observations.",
    "get_active_alarms": "Read active alarms and automatic protections.",
    "get_scenario_results": "Read completed isolated what-if simulations.",
    "submit_action_proposal": "Validate an alternative action combination in deterministic simulation. NEVER executes actions.",
    "submit_fault_hypothesis": "Record a fault hypothesis supported by evidence; does not inject a fault.",
    "submit_scenario_proposal": "Simulate hypothetical faults on an isolated copy; never affects playback.",
}


def tool_schemas():
    return [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
             "parameters": model.model_json_schema()}} for name, model in TOOL_MODELS.items()]


def validate_fault(spec, state, topo):
    params = faults.validate(topo, spec.type, spec.target, spec.params)
    catalog = faults.FAULT_CATALOG[spec.type]["params"]
    if set(spec.params) - set(catalog):
        raise ValueError("Unknown fault parameters")
    for key, rule in catalog.items():
        value = params[key]
        if "options" in rule:
            if value not in rule["options"]:
                raise ValueError(f"Invalid {key}")
        elif value is not None:
            if type(value) not in (int, float) or not rule["min"] <= value <= rule["max"]:
                raise ValueError(f"{key} is outside the supported range")
        elif rule.get("default") is not None:
            raise ValueError(f"{key} is required")
    if spec.type == "LEVEL_SENSOR_FAULT":
        if params["transmitter"] not in state.tanks[spec.target].level_sensors:
            raise ValueError("Transmitter does not exist")
        if params["mode"] == "stuck" and params["value"] is None:
            params["value"] = state.tanks[spec.target].level_sensors[params["transmitter"]] or 0.0
    return params


class Context:
    def __init__(self, session, audit):
        # Capture on the event-loop thread; workers see only private copies.
        self.run_id, self.revision = session.run_id, session.revision
        self.state = copy.deepcopy(session.state)
        self.state = replace(self.state, faults=tuple(f for f in self.state.faults if f.start_min <= self.state.t_min))
        self.cfg, self.topo = copy.deepcopy(session.cfg), copy.deepcopy(session.topo)
        self.engine_enabled = session.engine_enabled
        self.dto = copy.deepcopy(session.state_dict())
        self.dto["faults"] = [f for f in self.dto["faults"] if f["start_min"] <= self.state.t_min]
        self.events = copy.deepcopy(session.event_log[-100:])
        self.brief = copy.deepcopy(shift_brief(session))
        self.audit = audit
        self.evidence, self.proposals, self.scenarios, self.hypotheses = {}, [], [], []
        self._rec = None
        self._prefix = uuid4().hex[:12]

    def fact(self, source, path, value, label=None):
        identity = f"{self._prefix}-{len(self.evidence) + 1}"
        row = {"id": identity, "run_id": self.run_id, "revision": self.revision,
               "t_min": self.state.t_min, "source": source, "path": path,
               "label": label or path, "value": copy.deepcopy(value)}
        self.evidence[identity] = row
        return row

    def citations(self, ids):
        if not ids or any(i not in self.evidence for i in ids):
            raise ValueError("Evidence must reference observations from this analysis")

    def recommendation(self):
        if self._rec is None:
            self._rec = decision.recommend(self.state, self.topo, self.cfg, engine_enabled=self.engine_enabled)
        return self._rec

    def asset(self, asset_id):
        if asset_id not in self.topo.nodes:
            raise ValueError("Unknown asset")
        group = {"tank": "tanks", "pump": "pumps", "source": "sources", "pipeline": "pipelines", "treatment": "treatment"}[self.topo.kind(asset_id)]
        return self.fact("get_asset_state", f"state.{group}.{asset_id}", self.dto[group][asset_id], asset_id)

    def related(self, asset_id):
        if asset_id not in self.topo.nodes:
            raise ValueError("Unknown asset")
        related = copy.deepcopy(impact(self.topo, asset_id))
        connected = set([asset_id] + related["upstream"] + related["downstream"])
        treatments = connected.intersection(self.topo.treatments)
        related["shared_capacity_assets"] = sorted({n for tr in treatments for n in impact(self.topo, tr)["upstream"]} - connected)
        related["transfer_supported"] = False
        return related

    @staticmethod
    def option_summary(option):
        data = option.model_dump()
        if data["trajectory_summary"]:
            data["trajectory_summary"] = {t: {k: v for k, v in vals.items() if k != "series"}
                                          for t, vals in data["trajectory_summary"].items()}
        return data

    def execute(self, name, arguments):
        if name not in TOOL_MODELS:
            raise ValueError("Tool not allowed")
        args = TOOL_MODELS[name].model_validate(arguments)
        self.audit.record(self.run_id, "tool_call", {"name": name, "arguments": args.model_dump(), "revision": self.revision})
        if name == "get_shift_brief":
            result = self.fact(name, "shift.brief", self.brief, "Shift handoff")
        elif name == "get_network_state":
            result = {"graph": {"nodes": [{"id": n, "type": v["type"]} for n, v in self.topo.nodes.items()],
                                "edges": self.topo.edges}, "assets": [self.asset(a) for a in self.topo.nodes]}
        elif name == "get_asset_state":
            result = self.asset(args.asset_id)
        elif name == "get_impact":
            result = self.fact(name, f"impact.{args.asset_id}", self.related(args.asset_id))
        elif name == "get_forecast":
            fc = tank_forecasts(rollout(self.state, self.topo, self.cfg), self.topo, self.cfg)
            result = [self.fact(name, f"forecast.{t}", f.model_dump(exclude={"series"})) for t, f in fc.items()]
        elif name == "get_recommendations":
            rec = self.recommendation()
            result = {"ranking": self.fact(name, "recommendation.ranked_option_ids", rec.ranked_option_ids),
                      "baseline": self.fact(name, "recommendation.do_nothing_cost", rec.do_nothing_cost),
                      "options": [self.fact(name, f"recommendation.options.{o.action_id}", self.option_summary(o), o.label) for o in rec.options]}
        elif name == "get_active_alarms":
            result = [self.fact(name, f"alarms.{a['id']}", a) for a in self.dto["alarms"] if a["state"] != "CLEARED"]
            result += [self.fact(name, f"events.{e['id']}", e, e["text"]) for e in self.events if e["tag"] == "AUTO"][-12:]
        elif name == "get_event_history":
            rows = self.audit.read(limit=500)
            if args.asset_id:
                if args.asset_id not in self.topo.nodes:
                    raise ValueError("Unknown asset")
                rows = [r for r in rows if r["data"].get("asset", r["data"].get("asset_id")) == args.asset_id]
            result = [self.fact(name, f"history.{r['id']}", r) for r in rows[:args.limit]]
        elif name == "get_scenario_results":
            result = self.scenarios
        elif name == "submit_action_proposal":
            self.citations(args.evidence_ids)
            proposal = {"id": uuid4().hex, "kind": "action", "run_id": self.run_id, "revision": self.revision,
                        "t_min": self.state.t_min, "status": "PENDING", "actions": [a.model_dump() for a in args.actions],
                        "evidence_ids": args.evidence_ids, "reasons": [], "option": None, "origin": "NEMOTRON"}
            self.proposals.append(proposal)
            self.audit.record(self.run_id, "proposal", proposal)
            try:
                if not self.engine_enabled:
                    raise ValueError("Decision engine disabled")
                combo = [a.action() for a in args.actions]
                option = decision.evaluate_actions(self.state, self.topo, self.cfg, combo)
                proposal.update(status="VALIDATED" if option.feasible else "REJECTED",
                                option=option.model_dump(), reasons=[r.text for r in option.reasons])
                evidence = self.fact(name, f"proposals.{proposal['id']}.validation", self.option_summary(option), "Simulator validation")
                proposal["evidence_ids"] = [*args.evidence_ids, evidence["id"]]
            except ValueError as exc:
                proposal.update(status="REJECTED", reasons=[str(exc)])
            self.audit.record(self.run_id, "proposal", proposal)
            result = proposal
        elif name == "submit_fault_hypothesis":
            self.citations(args.evidence_ids)
            validate_fault(args.fault, self.state, self.topo)
            result = {"id": uuid4().hex, "kind": "hypothesis", "status": "VALIDATED", "run_id": self.run_id,
                      "t_min": self.state.t_min, **args.model_dump(), "meaning": "Valid hypothesis format; cause is unconfirmed. No fault injected."}
            self.hypotheses.append(result)
            self.audit.record(self.run_id, "hypothesis", result)
        elif name == "submit_scenario_proposal":
            altered = self.state
            for spec in args.faults:
                params = validate_fault(spec, altered, self.topo)
                altered = replace(altered, faults=altered.faults + (Fault(uuid4().hex, spec.type, spec.target, params, altered.t_min),))
            rec = decision.recommend(altered, self.topo, self.cfg, engine_enabled=self.engine_enabled)
            # The reference starts at the identical simulated minute with no hypothetical fault added.
            baseline = decision.recommend(self.state, self.topo, self.cfg, engine_enabled=False)
            result = {"id": uuid4().hex, "kind": "scenario", "status": "VALIDATED", "run_id": self.run_id,
                      "t_min": self.state.t_min, "faults": args.model_dump()["faults"],
                      "forecast": {t: f.model_dump(exclude={"series"}) for t, f in rec.forecast.items()},
                      "options": [self.option_summary(o) for o in rec.options], "best_option_id": rec.best_option_id,
                      "do_nothing_cost": rec.do_nothing_cost, "hypothetical": True,
                      "horizon_min": self.cfg.time.horizon_min,
                      "baseline": {"do_nothing_cost": baseline.do_nothing_cost,
                                   "forecast": {t: f.model_dump(exclude={"series"}) for t, f in baseline.forecast.items()}}}
            evidence = self.fact(name, f"scenarios.{result['id']}", result, "What-if simulation (not live)")
            result["evidence_ids"] = [evidence["id"]]
            self.scenarios.append(result)
            self.audit.record(self.run_id, "scenario", result)
        self.audit.record(self.run_id, "tool_result", {"name": name, "result": result})
        return result
