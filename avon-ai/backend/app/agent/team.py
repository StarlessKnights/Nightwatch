"""One event-triggered investigation. Both specialists observe the same frozen plant snapshot."""
import asyncio
import time
from dataclasses import asdict, dataclass, field
from uuid import uuid4

from .gateway import GatewayError
from .handoff import handoff_text


FLOW = "Thermal Capacity Agent"
PUMP = "Cooling Reliability Agent"
WORKLOAD = "Workload Placement Agent"
COORDINATOR = "Incident Commander"

PROMPTS = {
    FLOW: "Review IT load surges, hall heat gain versus heat removal, chilled-water loop resistance and heat-rejection restrictions. "
          "Explain the main imbalance and the next reading to check.",
    PUMP: "Review delivered chiller-pump flow, health, trips, availability and standby readiness. "
          "Distinguish a worn pump from a restriction in the loop or heat rejection. Availability alone does not prove backup capacity.",
    WORKLOAD: "Compare workload relief with cooling responses using the supplied validated options. "
              "Explain the thermal benefit and compute-service tradeoff. Destination capacity, job priorities and SLAs "
              "are not modeled: ask for these before recommending actual migration. Do not invent a destination or jobs.",
    COORDINATOR: "Combine all three specialist handoffs into an operator briefing. Identify the most pressing consequence, "
                 "how the flow and pump evidence relate, and one next check. Distinguish hypotheses from measurements. "
                 "If a material incident warrants an alternative, consult the ranking and submit it for validation.",
}


@dataclass
class Report:
    role: str
    model: str
    observation: str
    evidence_ids: list
    status: str = "Queued"
    source: str | None = None
    interpretations: list = field(default_factory=list)
    error: str | None = None
    focus_asset_ids: list = field(default_factory=list)
    tool_events: list = field(default_factory=list)
    started_at: float | None = None
    completed_at: float | None = None


class SpecialistContext:
    """A specialist may inspect its assigned equipment, never submit actions."""
    def __init__(self, ctx, report):
        self.ctx, self.report = ctx, report

    def __getattr__(self, name):
        return getattr(self.ctx, name)

    def execute(self, name, arguments):
        if name not in ("get_asset_state", "get_impact", "get_workload_plan"):
            raise ValueError("Specialists can only read assigned evidence")
        if name == "get_workload_plan":
            if self.report.role != WORKLOAD:
                raise ValueError("Workload comparison belongs to the workload specialist")
        elif arguments.get("asset_id") not in self.report.focus_asset_ids:
            raise ValueError("Asset outside this investigation's assigned scope")
        result = self.ctx.execute(name, arguments)
        ids = [result["id"]] if isinstance(result, dict) and "id" in result else []
        self.report.evidence_ids.extend(i for i in ids if i not in self.report.evidence_ids)
        for event in reversed(self.report.tool_events):
            if event["tool"] == name and event["status"] == "Consulting tool":
                event["evidence_ids"] = ids
                break
        return result


def flow_report(ctx, model, scope):
    groups = ("tanks", "sources", "pipelines", "treatment")
    ids = [ctx.asset(asset)["id"] for group in groups for asset in ctx.dto[group] if asset in scope]
    tanks = {a: v for a, v in ctx.dto["tanks"].items() if a in scope}
    rising = max(tanks, key=lambda t: tanks[t]["inflow"] - tanks[t]["outflow"], default=None)
    summary = "No hall has positive net heat gain."
    if rising:
        tank = tanks[rising]
        if tank["inflow"] > tank["outflow"]:
            summary = f"{rising} absorbs {tank['inflow']:g} kW of heat load while {tank['outflow']:g} kW is removed."
    surges = [a for a, v in ctx.dto["sources"].items() if a in scope and v["eff_rate"] > v["rate"]]
    restrictions = [a for a, v in ctx.dto["pipelines"].items() if a in scope and v["r"] > 1.01]
    restrictions.extend(a for a, v in ctx.dto["treatment"].items() if a in scope and v["intake_factor"] < 1)
    if surges:
        summary += " Elevated heat load at " + ", ".join(surges) + "."
    if restrictions:
        summary += " Restricted heat removal at " + ", ".join(restrictions) + "."
    return Report(FLOW, model, summary, ids)


def pump_report(ctx, model, scope):
    pumps = {a: v for a, v in ctx.dto["pumps"].items() if a in scope}
    ids = [ctx.asset(asset)["id"] for asset in pumps]
    findings = []
    for asset, p in pumps.items():
        if not p["available"] or p["run_state"] == "TRIPPED":
            findings.append(f"{asset} is {'tripped' if p['run_state'] == 'TRIPPED' else 'unavailable'}.")
        elif p["eff_capacity_factor"] < .99:
            findings.append(f"{asset} delivers {p['flow']:g} kW at {p['eff_capacity_factor']:.0%} effective capacity.")
        elif p["role"] == "standby":
            findings.append(f"{asset} is available, {p['run_state'].lower()}, delivering {p['flow']:g} kW.")
    return Report(PUMP, model, " ".join(findings) or "No chiller-pump trip, unavailability or loss of effective capacity detected.", ids)


class Investigation:
    def __init__(self, ctx, settings, trigger, active_incident, focus_assets=None):
        self.id = uuid4().hex
        self.run_id, self.t_min, self.revision = ctx.run_id, ctx.state.t_min, ctx.revision
        self.trigger = trigger
        self.active_incident = active_incident
        self.scope = set(focus_assets or ctx.topo.nodes)
        self.flow = flow_report(ctx, settings.routine_model, self.scope)
        self.pump = pump_report(ctx, settings.routine_model, self.scope)
        self.workload = Report(WORKLOAD, settings.routine_model,
            "Compare modeled workload relief against cooling capacity. Confirm destination headroom and workload priorities before migration.", [])
        self.coordinator = Report(COORDINATOR, settings.reasoning_model, "", [], status="Awaiting handoffs")
        self.scope = set(focus_assets or ctx.topo.nodes)
        for report in (self.flow, self.pump):
            report.evidence_ids = [i for i in report.evidence_ids if ctx.evidence[i]["label"] in self.scope]
            report.focus_asset_ids = [ctx.evidence[i]["label"] for i in report.evidence_ids]
        self.workload.focus_asset_ids = [a for a in self.scope if ctx.topo.kind(a) in ("source", "tank")]
        self.coordinator.focus_asset_ids = sorted(self.scope)
        self.events = []
        self.started = time.monotonic()

    def snapshot(self):
        return {"id": self.id, "run_id": self.run_id, "t_min": self.t_min, "revision": self.revision,
                "trigger": self.trigger, "reports": [asdict(r) for r in (self.flow, self.pump, self.workload, self.coordinator)],
                "events": list(self.events)}

    def transition(self, ctx, report, status):
        report.status = status
        elapsed = round(time.monotonic() - self.started, 1)
        if status == "Reviewing":
            report.started_at = elapsed
        else:
            report.completed_at = elapsed
        event = {"role": report.role, "status": status, "source": report.source,
                 "elapsed_s": round(time.monotonic() - self.started, 1)}
        self.events.append(event)
        ctx.audit.record(ctx.run_id, "agent_handoff", {"investigation": self.id, "t_min": self.t_min, **event})

    async def review(self, ctx, gateway, report):
        self.transition(ctx, report, "Reviewing")
        if report is self.workload:
            event = {"tool": "get_workload_plan", "status": "Running", "evidence_ids": []}
            report.tool_events.append(event)
            try:
                result = await asyncio.to_thread(ctx.execute, "get_workload_plan", {})
                report.evidence_ids = [result["id"]]
                event.update(status="Completed", evidence_ids=report.evidence_ids)
                report.observation = result["value"]["summary"]
            except Exception:
                event["status"] = "Unavailable"
        else:
            report.tool_events.extend({"tool": "get_asset_state", "status": "Completed", "evidence_ids": [i],
                                       "origin": "Observation adapter"} for i in report.evidence_ids
                                     if ctx.evidence[i]["source"] == "get_asset_state")
        if gateway.configured:
            try:
                seed = {"observed_at": self.t_min, "measured_summary": report.observation,
                        "readings": [ctx.evidence[i] for i in report.evidence_ids]}
                coordinator = report is self.coordinator
                def activity(status, tool):
                    if status != "Consulting tool" and report.tool_events and report.tool_events[-1]["tool"] == tool:
                        report.tool_events[-1]["status"] = status
                    else:
                        report.tool_events.append({"tool": tool, "status": status, "evidence_ids": []})
                prompt = (f"You are the {report.role}. {PROMPTS[report.role]} "
                          "Write one short qualitative interpretation. Leave readings, times and percentages "
                          "to the evidence cards. Refer to assets by role (the overheating hall, the standby chiller pump). "
                          "Use exact supplied evidence IDs in the citation fields only.")
                answer = await gateway.analyze(ctx if coordinator else SpecialistContext(ctx, report), prompt, seed,
                                               complex_task=coordinator, evidence_only=coordinator and not self.active_incident,
                                               tool_names=None if coordinator else ["get_asset_state", "get_impact"] + (["get_workload_plan"] if report is self.workload else []),
                                               activity=activity,
                                               explain_references=True)
                claims = [*answer.interpretations, *answer.concerns]
                allowed = ctx.evidence if coordinator else report.evidence_ids
                if not claims or any(set(c.evidence_ids) - set(allowed) for c in claims):
                    raise GatewayError("No interpretation grounded in the assigned readings")
                report.interpretations = [c.model_dump() for c in claims]
                report.source = "Nemotron"
            except Exception as exc:
                report.error = str(exc) if isinstance(exc, GatewayError) else "Model review unavailable"
        if not report.source:
            report.source = "Simulator rules"
        self.transition(ctx, report, "Brief ready" if report is self.coordinator else "Delivered")

    def handoff(self, ctx, report):
        value = {**asdict(report), "investigation_id": self.id, "observed_at_min": self.t_min,
                 "observation_revision": self.revision}
        return ctx.fact("agent_handoff", f"team.{self.id}.{report.role}", value, f"{report.role} report")

    async def run(self, ctx, gateways, current, publish):
        # Specialists can inspect assigned evidence; only the Commander can propose actions.
        async with asyncio.TaskGroup() as jobs:
            for report in (self.flow, self.pump, self.workload):
                jobs.create_task(self.review(ctx, gateways[report.role], report))
        if not current():
            return
        handoffs = [self.handoff(ctx, r) for r in (self.flow, self.pump, self.workload)]
        self.coordinator.evidence_ids = [row["id"] for row in handoffs]
        self.coordinator.observation = handoff_text(ctx.brief)
        publish(ctx)
        await self.review(ctx, gateways[COORDINATOR], self.coordinator)
        if self.coordinator.source == "Simulator rules":
            self.coordinator.interpretations = [
                {"text": r.observation, "evidence_ids": [h["id"]]} for r, h in zip((self.flow, self.pump, self.workload), handoffs)
            ]
