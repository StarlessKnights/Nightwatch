"""One event-triggered investigation. Both specialists observe the same frozen plant snapshot."""
import asyncio
import time
from dataclasses import asdict, dataclass, field
from uuid import uuid4

from .gateway import GatewayError
from .handoff import handoff_text


FLOW = "Inflow/Outflow Monitor"
PUMP = "Pump Monitor"
COORDINATOR = "Coordinator"

PROMPTS = {
    FLOW: "Review inflow surges, tank inflow versus outflow, pipeline resistance and treatment restrictions. "
          "Explain the main imbalance and the next reading to check.",
    PUMP: "Review delivered pump flow, health, trips, availability and standby readiness. "
          "Distinguish a worn pump from a downstream restriction. Availability alone does not prove backup capacity.",
    COORDINATOR: "Combine the two specialist handoffs into an operator briefing. Identify the most pressing consequence, "
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


def flow_report(ctx, model):
    groups = ("tanks", "sources", "pipelines", "treatment")
    ids = [ctx.asset(asset)["id"] for group in groups for asset in ctx.dto[group]]
    tanks = ctx.dto["tanks"]
    rising = max(tanks, key=lambda t: tanks[t]["inflow"] - tanks[t]["outflow"], default=None)
    summary = "No tank has positive net inflow."
    if rising:
        tank = tanks[rising]
        if tank["inflow"] > tank["outflow"]:
            summary = f"{rising} receives {tank['inflow']:g} bbl/hr and discharges {tank['outflow']:g} bbl/hr."
    surges = [a for a, v in ctx.dto["sources"].items() if v["eff_rate"] > v["rate"]]
    restrictions = [a for a, v in ctx.dto["pipelines"].items() if v["r"] > 1.01]
    restrictions.extend(a for a, v in ctx.dto["treatment"].items() if v["intake_factor"] < 1)
    if surges:
        summary += " Elevated inflow at " + ", ".join(surges) + "."
    if restrictions:
        summary += " Restricted discharge at " + ", ".join(restrictions) + "."
    return Report(FLOW, model, summary, ids)


def pump_report(ctx, model):
    pumps = ctx.dto["pumps"]
    ids = [ctx.asset(asset)["id"] for asset in pumps]
    findings = []
    for asset, p in pumps.items():
        if not p["available"] or p["run_state"] == "TRIPPED":
            findings.append(f"{asset} is {'tripped' if p['run_state'] == 'TRIPPED' else 'unavailable'}.")
        elif p["eff_capacity_factor"] < .99:
            findings.append(f"{asset} delivers {p['flow']:g} bbl/hr at {p['eff_capacity_factor']:.0%} effective capacity.")
        elif p["role"] == "standby":
            findings.append(f"{asset} is available, {p['run_state'].lower()}, delivering {p['flow']:g} bbl/hr.")
    return Report(PUMP, model, " ".join(findings) or "No pump trip, unavailability or loss of effective capacity detected.", ids)


class Investigation:
    def __init__(self, ctx, settings, trigger, active_incident):
        self.id = uuid4().hex
        self.run_id, self.t_min, self.revision = ctx.run_id, ctx.state.t_min, ctx.revision
        self.trigger = trigger
        self.active_incident = active_incident
        self.flow = flow_report(ctx, settings.routine_model)
        self.pump = pump_report(ctx, settings.routine_model)
        self.coordinator = Report(COORDINATOR, settings.reasoning_model, "", [], status="Awaiting handoffs")
        self.events = []
        self.started = time.monotonic()

    def snapshot(self):
        return {"id": self.id, "run_id": self.run_id, "t_min": self.t_min, "revision": self.revision,
                "trigger": self.trigger, "reports": [asdict(r) for r in (self.flow, self.pump, self.coordinator)],
                "events": list(self.events)}

    def transition(self, ctx, report, status):
        report.status = status
        event = {"role": report.role, "status": status, "source": report.source,
                 "elapsed_s": round(time.monotonic() - self.started, 1)}
        self.events.append(event)
        ctx.audit.record(ctx.run_id, "agent_handoff", {"investigation": self.id, "t_min": self.t_min, **event})

    async def review(self, ctx, gateway, report):
        self.transition(ctx, report, "Reviewing")
        if gateway.configured:
            try:
                seed = {"observed_at": self.t_min, "measured_summary": report.observation,
                        "readings": [ctx.evidence[i] for i in report.evidence_ids]}
                coordinator = report is self.coordinator
                prompt = (f"You are the {report.role}. {PROMPTS[report.role]} "
                          "Write one short qualitative interpretation. Leave readings, times and percentages "
                          "to the evidence cards. Refer to assets by role (the filling tank, the standby pump). "
                          "Use exact supplied evidence IDs in the citation fields only.")
                answer = await gateway.analyze(ctx, prompt, seed,
                                               complex_task=coordinator, evidence_only=not (coordinator and self.active_incident),
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
        # Specialists only read their own evidence and cannot call tools. No mutation of playback.
        async with asyncio.TaskGroup() as jobs:
            for report in (self.flow, self.pump):
                jobs.create_task(self.review(ctx, gateways[report.role], report))
        if not current():
            return
        handoffs = [self.handoff(ctx, r) for r in (self.flow, self.pump)]
        self.coordinator.evidence_ids = [row["id"] for row in handoffs]
        self.coordinator.observation = handoff_text(ctx.brief)
        publish(ctx)
        await self.review(ctx, gateways[COORDINATOR], self.coordinator)
        if self.coordinator.source == "Simulator rules":
            self.coordinator.interpretations = [
                {"text": r.observation, "evidence_ids": [h["id"]]} for r, h in zip((self.flow, self.pump), handoffs)
            ]
