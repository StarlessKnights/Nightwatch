import ast
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app import actions, decision
from app.agent.audit import Audit
from app.agent.gateway import Gateway, GatewayError
from app.agent.monitor import observe
from app.agent.orchestrator import Agent
from app.agent.settings import Settings
from app.agent.tools import Context
from app.agent.team import COORDINATOR, FLOW, PUMP
from app.session import Session


@pytest.fixture
def agent_setup(tmp_path):
    session = Session()
    session.load("scene2_pump_degraded")
    settings = Settings(audit_path=tmp_path / "audit.sqlite3", min_interval_s=1)
    agent = Agent(session, settings)
    return session, agent


@pytest.mark.parametrize("pump_offline", [False, True])
def test_specialists_parallel_then_coordinator_uses_both_reports(agent_setup, pump_offline):
    session, original = agent_setup
    settings = original.settings.model_copy(update={"api_key": Settings(api_key="test").api_key})
    started = set()
    both_started = asyncio.Event()
    async def handler(request):
        body = json.loads(request.content)
        inputs = json.loads(body["messages"][1]["content"])
        role = next(role for role in (FLOW, PUMP, COORDINATOR) if inputs["request"].startswith(f"You are the {role}."))
        readings = inputs["observation"]["readings"]
        if role == COORDINATOR:
            assert body["model"] == settings.reasoning_model
            assert [r["value"]["role"] for r in readings] == [FLOW, PUMP]
            assert [r["value"]["source"] for r in readings] == ["Nemotron", "Simulator rules" if pump_offline else "Nemotron"]
        else:
            assert body["model"] == settings.routine_model and "tools" not in body
            assert all(("state.pumps." in r["path"]) == (role == PUMP) for r in readings)
            started.add(role)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=3)
            if pump_offline and role == PUMP:
                return httpx.Response(401)
        ids = [r["id"] for r in readings[:2]]
        answer = {"evidence_ids": ids, "interpretations": [{"text": "Inspect the observed change.", "evidence_ids": ids}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    agent = Agent(session, settings, Gateway(settings, original.audit, httpx.MockTransport(handler)))
    async def run():
        signature, groups = observe(session)
        await agent.analyze_observation(Context(session, agent.audit), groups, signature)
        await agent.model_task
        team = agent.snapshot()["team"]
        assert [e["status"] for e in team["events"]] == ["Reviewing", "Reviewing", "Delivered", "Delivered", "Reviewing", "Brief ready"]
        assert team["reports"][-1]["source"] == "Nemotron"
        assert not agent.messages and not session.state.pending_actions
        for report in team["reports"]:
            assert all(id in agent.evidence for id in report["evidence_ids"])
        session.reset()
        assert agent.snapshot()["team"] is None
    asyncio.run(run())


def test_tools_cannot_actuate_or_see_future_faults(agent_setup):
    session, agent = agent_setup
    session.load("scene4_pump_trip")
    ctx = Context(session, agent.audit)
    assert ctx.state.faults == () and ctx.dto["faults"] == []
    before = session.state
    with pytest.raises(ValueError, match="not allowed"):
        ctx.execute("approve", {})
    ctx.execute("submit_scenario_proposal", {"faults": [{"type": "PUMP_UNAVAILABLE", "target": "P-204"}]})
    assert session.state is before
    assert ctx.scenarios[0]["hypothetical"]


@pytest.mark.parametrize("fault", [
    {"type": "PUMP_DEGRADE", "target": "P-203", "params": {"factor": 2}},
    {"type": "PUMP_DEGRADE", "target": "P-203", "params": {"factor": float("nan")}},
    {"type": "PUMP_TRIP", "target": "T-104"},
    {"type": "PUMP_TRIP", "target": "P-203", "params": {"override": True}},
    {"type": "LEVEL_SENSOR_FAULT", "target": "T-101", "params": {"transmitter": "B"}},
])
def test_scenario_rejects_invalid_faults(agent_setup, fault):
    session, agent = agent_setup
    before = session.state
    with pytest.raises(ValueError):
        Context(session, agent.audit).execute("submit_scenario_proposal", {"faults": [fault]})
    assert session.state is before


def test_proposal_matches_deterministic_engine_and_requires_approval(agent_setup):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    evidence = ctx.asset("P-203")
    original = decision.recommend(ctx.state, ctx.topo, ctx.cfg)
    p = ctx.execute("submit_action_proposal", {"actions": [{"kind": "START_STANDBY_PUMP", "target": "P-204"}], "evidence_ids": [evidence["id"]]})
    assert p["status"] == "VALIDATED"
    assert p["option"] == next(o.model_dump() for o in original.options if o.action_id == "START_STANDBY_PUMP:P-204")
    assert not session.state.pending_actions
    agent.publish_context(ctx)
    async def approve():
        await agent.decide(p["id"], True, session.run_id)
        with pytest.raises(ValueError):
            await agent.decide(p["id"], True, session.run_id)
    asyncio.run(approve())
    assert len(session.state.pending_actions) == 1
    session.advance(5)
    agent.collect_events()
    assert p["status"] == "EXECUTED_IN_SIM"


def test_revalidation_rejects_newly_unavailable_pump(agent_setup):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    evidence = ctx.asset("P-203")
    p = ctx.execute("submit_action_proposal", {"actions": [{"kind": "START_STANDBY_PUMP", "target": "P-204"}], "evidence_ids": [evidence["id"]]})
    agent.publish_context(ctx)
    session.patch_asset("P-204", None, False)
    asyncio.run(agent.decide(p["id"], True, session.run_id))
    assert p["status"] == "REJECTED" and not session.state.pending_actions


def test_conflicts_and_unknown_evidence_rejected(agent_setup):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    with pytest.raises(ValueError, match="Evidence"):
        ctx.execute("submit_action_proposal", {"actions": [{"kind": "START_STANDBY_PUMP", "target": "P-204"}], "evidence_ids": ["invented"]})
    a = actions.Action("REDUCE_PRODUCTION", {"source": "SRC-1", "pct": 40})
    with pytest.raises(ValueError, match="Conflicting"):
        decision.evaluate_actions(ctx.state, ctx.topo, ctx.cfg, [a, a])


def test_monitor_deduplicates_and_resets(agent_setup):
    session, agent = agent_setup
    async def run():
        signature, groups = observe(session)
        assert len(groups) == 1
        ctx = Context(session, agent.audit)
        await agent.analyze_observation(ctx, groups, signature)
        identity = agent.incidents[0]["id"]
        await agent.analyze_observation(Context(session, agent.audit), groups, signature)
        assert len(agent.incidents) == 1 and agent.incidents[0]["id"] == identity
        assert not agent.proposals  # The engine's ranked action is not a second Intelligence proposal.
        old_run = session.run_id
        session.reset()
        agent.reset_run()
        assert not agent.incidents and not agent.proposals and old_run != session.run_id
        assert not agent.publish_context(ctx)
    asyncio.run(run())


def test_forecast_keeps_actual_timestamp(agent_setup):
    session, _ = agent_setup
    session.advance()
    assert session.snapshot()["forecast"]["as_of_min"] == 0


def test_no_agent_imports_in_physics_or_safety():
    root = Path(__file__).resolve().parents[1]
    visited = set()
    def check(name):
        if name in visited or not (root / f"{name}.py").exists(): return
        visited.add(name)
        tree = ast.parse((root / f"{name}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "agent" not in (node.module or "")
                if node.level:
                    for child in ([node.module.split('.')[0]] if node.module else [a.name for a in node.names]):
                        assert child != "agent"
                        check(child)
            elif isinstance(node, ast.Import):
                assert all("agent" not in a.name.split('.') for a in node.names)
    for name in ("sim", "control", "interlock", "flow"): check(name)


def test_disabled_agent_leaves_safety_operational(agent_setup):
    session, agent = agent_setup
    agent.enabled = False
    session.load("scene6_interlock_only")
    async def run():
        agent.start()
        session.advance(60)
        await asyncio.sleep(.02)
        await agent.close()
    asyncio.run(run())
    assert session.state.interlocks["T-104"].tripped
    assert not agent.incidents


def test_gateway_tool_loop_and_evidence_validation(agent_setup):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            message = {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_asset_state", "arguments": '{"asset_id":"P-203"}'}}]}
        else:
            message = {"content": json.dumps({"evidence_ids": list(ctx.evidence), "interpretations": [], "concerns": [], "question": None})}
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
    gateway = Gateway(Settings(api_key="secret-test", audit_path=agent.settings.audit_path), agent.audit, httpx.MockTransport(handler))
    result = asyncio.run(gateway.analyze(ctx, "Why?", {}))
    assert result.evidence_ids and count == 2
    assert "secret-test" not in json.dumps(agent.audit.read(kinds=("llm_request", "llm_response")))


@pytest.mark.parametrize("mode", ["invalid_json", "bad_evidence", "timeout", "auth"])
def test_gateway_fails_closed(agent_setup, mode):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    def handler(request):
        if mode == "timeout": raise httpx.ReadTimeout("timeout", request=request)
        if mode == "auth": return httpx.Response(401, text="secret-test")
        content = "not json" if mode == "invalid_json" else '{"evidence_ids":["invented"]}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    gateway = Gateway(Settings(api_key="secret-test", audit_path=agent.settings.audit_path), agent.audit, httpx.MockTransport(handler))
    with pytest.raises(GatewayError):
        asyncio.run(gateway.analyze(ctx, "Why?", {}))
    assert not session.state.pending_actions
    assert "secret-test" not in gateway.last_error


def test_gateway_repairs_quantities_but_accepts_cited_equipment_tag(agent_setup):
    session, agent = agent_setup
    ctx = Context(session, agent.audit)
    seed = ctx.asset("P-203")
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        prose = "P-203 lost 99 bbl." if len(calls) == 1 else "Check whether P-203 output recovers."
        answer = {"evidence_ids": [seed["id"]], "interpretations": [{"text": prose, "evidence_ids": [seed["id"]]}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
    gateway = Gateway(Settings(api_key="test"), agent.audit, httpx.MockTransport(handler))
    answer = asyncio.run(gateway.analyze(ctx, "What changed?", seed))
    assert answer.interpretations[0].text == "Check whether P-203 output recovers."
    assert len(calls) == 2 and "tools" not in calls[1] and calls[1]["response_format"]["type"] == "json_object"


def test_fallback_chat_simulates_without_mutation(agent_setup):
    session, agent = agent_setup
    before = session.state
    ctx = Context(session, agent.audit)
    answer = asyncio.run(agent.fallback_chat(ctx, "What happens if treatment capacity drops by 50%?", None))
    assert answer.evidence_ids and ctx.scenarios[0]["faults"][0]["params"]["factor"] == .5
    result = ctx.scenarios[0]
    reference = decision.recommend(before, ctx.topo, ctx.cfg, engine_enabled=False)
    assert result["baseline"]["do_nothing_cost"] == reference.do_nothing_cost
    assert {t: f["time_to_HH"] for t, f in result["baseline"]["forecast"].items()} == {
        t: f.time_to_HH for t, f in reference.forecast.items()}
    assert {"T-104", "T-101"} <= result["forecast"].keys()
    assert session.state is before


def test_shift_brief_uses_only_observed_window_and_current_run(agent_setup):
    session, agent = agent_setup
    session.advance(36)
    ctx = Context(session, agent.audit)
    fact = ctx.execute("get_shift_brief", {})
    brief = fact["value"]
    assert fact["run_id"] == session.run_id and brief["from_min"] == 6
    for row in brief["trends"]:
        assert len(row["samples"]) == 31 and row["samples"][-1]["t"] == 36
        assert row["change_bbl"] == round(session.history[-1][row["tank"]] - session.history[-31][row["tank"]], 2)
    assert brief["forecast_as_of"] == 0
    assert all(6 <= e["t_min"] <= 36 for e in brief["recent_events"])
    answer = asyncio.run(agent.fallback_chat(ctx, "What changed this shift?", None))
    assert any(ctx.evidence[k]["source"] == "get_shift_brief" for k in answer.evidence_ids)
    session.reset()
    new = agent.snapshot()["shift_brief"]
    assert new["run_id"] != brief["run_id"] and new["t_min"] == 0
    assert all(len(t["samples"]) == 1 for t in new["trends"])


def test_audit_failure_does_not_break_monitor(agent_setup, tmp_path):
    session, agent = agent_setup
    parent = tmp_path / "file"
    parent.write_text("not a directory")
    broken = Audit(parent / "audit.sqlite3")
    broken.record(session.run_id, "event", {})
    assert broken.error
    assert broken.read() == []
