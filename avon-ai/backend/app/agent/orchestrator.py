"""Single bounded analysis worker, durable audit, proposals and operator interaction."""
import asyncio
import contextlib
import re
import time
from uuid import uuid4

from .. import decision
from .audit import Audit
from .gateway import Gateway, GatewayError
from .history import signals
from .handoff import HANDOFF_TERMS, handoff_text, operator_read, shift_brief
from .incidents import briefing
from .monitor import observe
from .proposals import ActionSpec, AgentAnswer
from .settings import Settings
from .tools import Context


class Agent:
    def __init__(self, session, settings=None, gateway=None):
        self.session, self.settings = session, settings or Settings.from_env()
        self.audit = Audit(self.settings.audit_path)
        self.gateway = gateway or Gateway(self.settings, self.audit)
        self.enabled = self.settings.enabled
        self.wake = asyncio.Event()
        self.worker = None
        self.run_id = session.run_id
        self.incidents, self.proposals, self.activity, self.messages, self.scenarios = [], [], [], [], []
        self.hypotheses, self.evidence = [], {}
        self.signature = None
        self.last_model_at = 0.0
        self.event_cursor = 0
        self.analyzing = False
        self.error = None
        self.lock = asyncio.Lock()
        self.chat_task = None
        self.model_task = None
        self.pending_model = False
        self.last_observation = None

    def record_activity(self, title, detail=""):
        item = {"id": uuid4().hex, "t_min": self.session.state.t_min, "title": title, "detail": detail}
        self.activity.append(item)
        self.activity = self.activity[-100:]
        self.audit.record(self.run_id, "activity", item)

    def start(self):
        if self.worker is None:
            self.session.listeners.append(self.wake.set)
            self.worker = asyncio.create_task(self.loop())
            self.wake.set()

    async def close(self):
        if self.wake.set in self.session.listeners:
            self.session.listeners.remove(self.wake.set)
        tasks = [t for t in (self.worker, self.chat_task, self.model_task) if t]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.worker = None

    def reset_run(self):
        if self.run_id == self.session.run_id:
            return
        for incident in self.incidents:
            if incident["status"] == "active":
                self.audit.record(self.run_id, "incident_closed", {**incident, "status": "closed", "reason": "Scenario reset"})
        for proposal in self.proposals:
            if proposal["status"] in ("PENDING", "VALIDATED", "APPROVED"):
                self.audit.record(self.run_id, "proposal", {**proposal, "status": "REJECTED", "reasons": ["Scenario reset"]})
        self.run_id = self.session.run_id
        self.incidents, self.proposals, self.messages, self.scenarios, self.hypotheses = [], [], [], [], []
        self.evidence, self.signature, self.event_cursor = {}, None, 0
        self.last_model_at = 0
        self.pending_model = False
        self.record_activity("Observation reset", "New simulation run")

    def collect_events(self):
        for event in self.session.event_log:
            if event["id"] <= self.event_cursor:
                continue
            self.audit.record(self.run_id, "event", event, f"event:{self.run_id}:{event['id']}")
            for proposal in self.proposals:
                if proposal["status"] != "APPROVED" or event["id"] <= proposal.get("approved_event_id", 0):
                    continue
                labels = [ActionSpec.model_validate(a).action().label for a in proposal["actions"]]
                if event["code"] in ("ACTION_EFFECTIVE", "ACTION_SKIPPED") and event["params"].get("label") in labels:
                    outcomes = proposal.setdefault("outcomes", {})
                    outcomes[event["params"]["label"]] = event
                    if event["code"] == "ACTION_SKIPPED":
                        proposal.update(status="REJECTED", reasons=["Scheduled action was skipped in simulation; inspect outcomes"])
                    elif len(outcomes) == len(labels):
                        proposal["status"] = "EXECUTED_IN_SIM"
                    self.audit.record(self.run_id, "proposal", proposal)
            self.event_cursor = event["id"]

    def publish_context(self, ctx):
        if ctx.run_id != self.session.run_id:
            return False
        for identity, evidence in ctx.evidence.items():
            self.evidence[identity] = evidence
            self.audit.record(ctx.run_id, "evidence", evidence, identity)
        for proposal in ctx.proposals:
            if not any(p["id"] == proposal["id"] or (p.get("actions") == proposal["actions"] and p["status"] in ("PENDING", "VALIDATED", "APPROVED") ) for p in self.proposals):
                self.proposals.append(proposal)
        for source, target in ((ctx.scenarios, self.scenarios), (ctx.hypotheses, self.hypotheses)):
            existing = {item["id"] for item in target}
            target.extend(item for item in source if item["id"] not in existing)
        self.scenarios, self.hypotheses = self.scenarios[-20:], self.hypotheses[-30:]
        self.proposals = self.proposals[-100:]
        # Retain all evidence referenced by the bounded visible collections.
        references = set()
        def scan(value):
            if isinstance(value, dict):
                references.update(value.get("evidence_ids", []))
                for v in value.values(): scan(v)
            elif isinstance(value, list):
                for v in value: scan(v)
        scan([self.incidents, self.proposals, self.messages, self.scenarios, self.hypotheses])
        self.evidence = {k: v for k, v in self.evidence.items() if k in references or k in ctx.evidence}
        return True

    async def loop(self):
        while True:
            try:
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=2)
                except TimeoutError:
                    pass
                self.wake.clear()
                self.reset_run()
                if not self.enabled:
                    continue
                self.collect_events()
                signature, groups = observe(self.session)
                due = self.pending_model and time.monotonic() - self.last_model_at >= self.settings.min_interval_s and not (self.model_task and not self.model_task.done())
                if signature == self.signature and not due:
                    continue
                # Coalesce changes while an analysis is running; never build a tick backlog.
                self.signature = signature
                ctx = Context(self.session, self.audit)
                self.record_activity("Meaningful change detected", ", ".join(r for g in groups for r in g["roots"]) or "Network recovered")
                await self.analyze_observation(ctx, groups, signature)
                self.last_observation = ctx.state.t_min
                self.error = None
            except asyncio.CancelledError:
                raise
            except Exception:
                self.error = "Analysis unavailable; simulation and automatic protection continue"
                self.record_activity("Agent fallback", self.error)

    async def analyze_observation(self, ctx, groups, signature):
        new = await asyncio.to_thread(lambda: [briefing(ctx, g) for g in groups])
        if ctx.run_id != self.session.run_id:
            return
        matched = set()
        for item in new:
            previous = next((i for i in self.incidents if i["status"] == "active" and i["id"] not in matched and
                             (set(i["roots"]) & set(item["roots"]) or set(i["tanks"]) & set(item["tanks"]))), None)
            if previous:
                item.update(id=previous["id"], first_seen_min=previous["first_seen_min"])
                self.incidents.remove(previous)
            matched.add(item["id"])
            self.incidents.insert(0, item)
        for old in self.incidents:
            if old["status"] == "active" and old["id"] not in matched:
                old.update(status="resolved", resolved_min=ctx.state.t_min,
                           post_incident_summary="Observed conditions cleared. Review the retained evidence and automatic response history.")
                self.audit.record(ctx.run_id, "incident_resolved", old)
        self.incidents = self.incidents[:40]
        self.publish_context(ctx)
        for item in new:
            self.audit.record(ctx.run_id, "incident", item)
        if not groups or not self.gateway.configured:
            return
        if time.monotonic() - self.last_model_at < self.settings.min_interval_s or (self.model_task and not self.model_task.done()):
            # Keep a lightweight periodic retry for the latest coalesced condition.
            self.pending_model = True
            return
        self.pending_model = False
        self.last_model_at = time.monotonic()
        seed = {"run_id": ctx.run_id, "as_of_min": ctx.state.t_min,
                "incidents": [{k: v for k, v in i.items() if k not in ("automatic", "concerns")} for i in new],
                "evidence": list(ctx.evidence.values())}
        self.model_task = asyncio.create_task(self.enrich(ctx, new, groups, signature, seed))

    async def enrich(self, ctx, new, groups, signature, seed):
        answer = None
        try:
            answer = await self.gateway.analyze(ctx, "Investigate these incidents. Use measured trends and event order to distinguish observed changes from possible causes. Identify what the operator should check next. Propose an alternative only if it addresses a gap in the ranked options.", seed,
                                                complex_task=any(i["severity"] == "critical" for i in new) or len(groups) > 1,
                                                activity=self.record_activity)
        except GatewayError as exc:
            self.record_activity("Nemotron fallback", str(exc))
        except Exception:
            self.record_activity("Nemotron fallback", "Unexpected provider failure")
        if ctx.run_id != self.session.run_id:
            return
        if observe(self.session)[0] != signature:
            self.record_activity("Outdated model result discarded", "A material network condition changed")
            self.signature = None
            return
        if answer:
            for item in new:
                item.update(source="NEMOTRON", interpretations=[x.model_dump() for x in answer.interpretations],
                            concerns=item["concerns"] + [x.model_dump() for x in answer.concerns], question=answer.question)
                item["evidence_ids"] = list(dict.fromkeys(item["evidence_ids"] + answer.evidence_ids))
                self.audit.record(ctx.run_id, "incident", item)
        self.publish_context(ctx)

    def submit_chat(self, message):
        if not self.enabled:
            raise ValueError("Enable intelligence monitoring first")
        if self.chat_task and not self.chat_task.done():
            raise ValueError("An operator question is already being analyzed")
        self.reset_run()
        entry = {"id": uuid4().hex, "role": "operator", "text": message, "t_min": self.session.state.t_min,
                 "run_id": self.run_id, "evidence_ids": []}
        self.messages.append(entry)
        self.audit.record(self.run_id, "operator_question", entry)
        self.chat_task = asyncio.create_task(self.chat(message, self.run_id))
        return entry

    async def chat(self, message, run_id):
        try:
            async with self.lock:
                if run_id != self.session.run_id:
                    return
                self.analyzing = True
                ctx = Context(self.session, self.audit)
                target = next((a for a in ctx.topo.nodes if a.lower() in message.lower()), None)
                handover = any(term in message.lower() for term in HANDOFF_TERMS)
                seed_tool = "get_shift_brief" if handover else "get_asset_state" if target else "get_forecast"
                seed = await asyncio.to_thread(ctx.execute, seed_tool, {"asset_id": target} if seed_tool == "get_asset_state" else {})
                rundown = handover and not target and not any(term in message.lower() for term in
                    ("what if", "what happens", "simulate", "scenario", "propose", "alternative", "history"))
                readings = [seed]
                if rundown:
                    if ctx.brief["trends"]:
                        readings.append(ctx.asset(ctx.brief["trends"][0]["tank"]))
                    if ctx.brief["recent_events"]:
                        event = ctx.brief["recent_events"][0]
                        readings.append(ctx.fact("get_event_history", f"events.{event['id']}", event, event["text"]))
                source = "NEMOTRON"
                try:
                    answer = await self.gateway.analyze(ctx, message, {"evidence": readings if rundown else seed, "as_of_min": ctx.state.t_min,
                        "previous_messages": [{"role": m["role"], "text": m.get("text", ""), "question": m.get("question")} for m in self.messages[-6:]]},
                        complex_task=True, activity=self.record_activity,
                        evidence_only=rundown,
                        explain_references=True)
                except Exception as exc:
                    source = "DETERMINISTIC"
                    self.record_activity("Nemotron fallback", str(exc) if isinstance(exc, GatewayError) else "Provider did not return an answer")
                    try:
                        answer = AgentAnswer() if rundown else await self.fallback_chat(ctx, message, target)
                    except Exception:
                        answer = AgentAnswer()
                    fact, assessment = operator_read(ctx)
                    answer.evidence_ids = [fact["id"], *answer.evidence_ids][:20]
                    answer.interpretations = AgentAnswer(interpretations=[{"text": assessment, "evidence_ids": [fact["id"]]}]).interpretations
                text = "Analysis based on the recorded observation."
                if handover:
                    text = handoff_text(seed["value"])
                entry = {"id": uuid4().hex, "role": "agent", "text": text,
                         "source": source, "t_min": ctx.state.t_min, "run_id": ctx.run_id, **answer.model_dump()}
                if ctx.run_id != self.session.run_id:
                    return
                self.messages.append(entry)
                self.messages = self.messages[-40:]
                self.publish_context(ctx)
                self.audit.record(ctx.run_id, "operator_answer", entry)
        except asyncio.CancelledError:
            raise
        except Exception:
            if run_id == self.session.run_id:
                fallback = Context(self.session, self.audit)
                fact, assessment = operator_read(fallback)
                entry = {"id": uuid4().hex, "run_id": run_id, "role": "agent", "source": "DETERMINISTIC",
                         "text": handoff_text(fallback.brief), "evidence_ids": [fact["id"]],
                         "interpretations": [{"text": assessment, "evidence_ids": [fact["id"]]}],
                         "t_min": fallback.state.t_min}
                self.messages.append(entry)
                self.messages = self.messages[-40:]
                self.publish_context(fallback)
                self.audit.record(run_id, "operator_answer", entry)
        finally:
            self.analyzing = False
            self.wake.set()

    async def fallback_chat(self, ctx, message, target):
        lower = message.lower()
        question = None
        if any(x in lower for x in ("what if", "what happens", "simulate", "scenario")):
            if target is None and "treatment" in lower:
                target = next(iter(ctx.topo.treatments), None)
            spec = None
            if target and ctx.topo.kind(target) == "pump" and any(x in lower for x in ("unavailable", "trip", "fail")):
                spec = {"type": "PUMP_UNAVAILABLE" if "unavailable" in lower else "PUMP_TRIP", "target": target}
            elif target and ctx.topo.kind(target) == "treatment":
                pct = re.search(r"(\d+(?:\.\d+)?)\s*%", lower)
                if pct:
                    factor = float(pct[1]) / 100
                    if "by " in lower or "drops " in lower or "reduces " in lower:
                        factor = 1 - factor
                    spec = {"type": "TREATMENT_CONSTRAINT", "target": target, "params": {"factor": factor}}
            if spec:
                await asyncio.to_thread(ctx.execute, "submit_scenario_proposal", {"faults": [spec]})
            else:
                question = "Which asset and fault should I simulate? For example: P-204 unavailable, or treatment capacity drops by 50%."
        elif any(x in lower for x in HANDOFF_TERMS):
            if not any(e["source"] == "get_shift_brief" for e in ctx.evidence.values()):
                await asyncio.to_thread(ctx.execute, "get_shift_brief", {})
        elif "history" in lower or "maintenance" in lower or "repeated" in lower:
            await asyncio.to_thread(ctx.execute, "get_event_history", {"asset_id": target, "limit": 10})
        else:
            if target:
                await asyncio.to_thread(ctx.execute, "get_impact", {"asset_id": target})
            await asyncio.to_thread(ctx.execute, "get_forecast", {})
            await asyncio.to_thread(ctx.execute, "get_recommendations", {})
        return AgentAnswer(evidence_ids=list(ctx.evidence)[-15:], question=question)

    async def decide(self, identity, approve, run_id):
        self.reset_run()
        if run_id != self.run_id:
            raise ValueError("Proposal belongs to an earlier simulation run")
        proposal = next((p for p in self.proposals if p["id"] == identity), None)
        if not proposal:
            raise KeyError(identity)
        if proposal["status"] != "VALIDATED":
            raise ValueError("Only a validated, unconsumed proposal can be decided")
        if not approve:
            proposal.update(status="REJECTED", reasons=["Operator rejected"])
        else:
            if not self.enabled or not self.session.engine_enabled:
                raise ValueError("Agent and decision engine must be enabled for approval")
            ctx = Context(self.session, self.audit)
            combo = [ActionSpec.model_validate(a).action() for a in proposal["actions"]]
            option = await asyncio.to_thread(decision.evaluate_actions, ctx.state, ctx.topo, ctx.cfg, combo)
            if proposal["status"] != "VALIDATED" or ctx.run_id != self.session.run_id:
                raise ValueError("Proposal already decided or scenario changed")
            if self.session.revision != ctx.revision:
                raise ValueError("State changed during validation; retry or pause playback before approving")
            if not option.feasible:
                proposal.update(status="REJECTED", option=option.model_dump(), reasons=[r.text for r in option.reasons])
                self.audit.record(self.run_id, "operator_decision", proposal)
                return proposal
            self.session.commit_verified_actions(combo, option, ctx.revision)
            proposal.update(status="APPROVED", option=option.model_dump(), approved_event_id=self.session._event_seq,
                            approved_min=self.session.state.t_min, validation_revision=ctx.revision)
        self.audit.record(self.run_id, "operator_decision", proposal)
        self.record_activity("Operator approved" if approve else "Operator rejected", identity)
        return proposal

    def snapshot(self):
        self.reset_run()
        active = [i for i in self.incidents if i["status"] == "active"]
        waiting = any(i.get("question") for i in active) or bool(self.messages and self.messages[-1].get("question"))
        busy = self.analyzing or bool(self.model_task and not self.model_task.done())
        status = "Disabled" if not self.enabled else "Analyzing" if busy else "Awaiting operator input" if waiting else "Incident detected" if active else "Monitoring"
        return {"run_id": self.run_id, "enabled": self.enabled, "status": status,
                "provider": "Nemotron" if self.gateway.configured else "Deterministic fallback",
                "model": self.settings.routine_model, "reasoning_model": self.settings.reasoning_model,
                "provider_error": self.gateway.last_error, "error": self.error, "audit_error": self.audit.error,
                "last_observation_min": self.last_observation, "incidents": self.incidents, "proposals": self.proposals,
                "shift_brief": shift_brief(self.session) if self.enabled else None,
                "activity": self.activity[-40:], "messages": self.messages, "scenarios": self.scenarios,
                "hypotheses": self.hypotheses, "evidence": self.evidence,
                "chat_busy": bool(self.chat_task and not self.chat_task.done())}
