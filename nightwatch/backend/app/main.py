"""Routes + websocket. Thin: all logic lives in session.py and the pure modules."""
from __future__ import annotations

import asyncio
import contextlib
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import faults, messages
from .decision import recommend
from .models import AssetPatch, EngineRequest, FaultRequest, HardwareStatusRequest, SpeedRequest
from .scenarios import list_scenarios
from .session import Session
from .agent.orchestrator import Agent
from .agent.proposals import ChatRequest, DecisionRequest, NoteRequest, ScenarioProposal, ToggleRequest
from .agent.tools import Context
from .agent.history import signals

TICK_REAL_S = 0.1

session = Session()
agent = Agent(session)
clients: set[WebSocket] = set()


async def broadcast(sync: bool = False) -> None:
    if not clients:
        return
    msg = session.sync_message() if sync else session.tick_message()
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            clients.discard(ws)


async def sim_loop() -> None:
    acc, last_fc = 0.0, 0.0
    while True:
        await asyncio.sleep(TICK_REAL_S)
        if not session.running:
            acc = 0.0
            continue
        acc += session.speed * TICK_REAL_S  # 1x = 1 sim-minute per real second
        n = int(acc)
        if n < 1:
            continue
        acc -= n
        session.advance(n)
        now = time.monotonic()
        if now - last_fc >= session.cfg.ui.ws_forecast_min_interval_s:
            session.refresh_forecast()
            last_fc = now
        await broadcast()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(sim_loop())
    agent.start()
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await agent.close()


app = FastAPI(title="NIGHTWATCH", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _topology_dict() -> dict:
    return {"nodes": list(session.topo.nodes.values()),
            "edges": [{"from": a, "to": b, "kind": k} for a, b, k in session.topo.edges]}


@app.get("/api/network")
def get_network():
    return {"topology": _topology_dict(), "config": session.cfg.model_dump(), "fault_catalog": faults.FAULT_CATALOG,
            "scenarios": list_scenarios(), "snapshot": session.snapshot()}


@app.get("/api/scenarios")
def get_scenarios():
    return list_scenarios()


@app.post("/api/sim/start")
async def sim_start():
    session.running = True
    session.start_duty_pumps()
    await broadcast()
    return {"running": True}


@app.post("/api/sim/pause")
async def sim_pause():
    session.running = False
    await broadcast()
    return {"running": False}


@app.post("/api/sim/step")
async def sim_step():
    session.running = False
    session.advance(1)
    session.refresh_forecast()
    await broadcast()
    return {"t_min": session.state.t_min}


@app.post("/api/sim/reset")
async def sim_reset():
    session.reset()
    await broadcast(sync=True)
    return {"t_min": 0}


@app.post("/api/sim/speed")
async def sim_speed(req: SpeedRequest):
    if req.x not in session.cfg.ui.speeds:
        raise HTTPException(400, "unsupported speed")
    session.speed = req.x
    await broadcast()
    return {"speed": req.x}


@app.post("/api/sim/engine")
async def sim_engine(req: EngineRequest):
    session.set_engine(req.enabled)
    await broadcast()
    return {"engine_enabled": req.enabled}


@app.post("/api/scenarios/{scenario_id}/load")
async def load_scenario_route(scenario_id: str):
    try:
        session.load(scenario_id)
    except KeyError:
        raise HTTPException(404, "unknown scenario")
    await broadcast(sync=True)
    return {"scenario": scenario_id}


@app.post("/api/faults")
async def post_fault(req: FaultRequest):
    try:
        f = session.inject_fault(req.type, req.target, req.params, req.end_min)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await broadcast()
    return {"id": f.id}


@app.delete("/api/faults/{fault_id}")
async def delete_fault(fault_id: str):
    try:
        session.clear_fault(fault_id)
    except KeyError:
        raise HTTPException(404, "unknown fault")
    await broadcast()
    return {"cleared": fault_id}


@app.patch("/api/assets/{asset_id}")
async def patch_asset(asset_id: str, req: AssetPatch):
    try:
        session.patch_asset(
            asset_id=asset_id,
            health=req.health if req.health is not None else req.capacity_factor,
            available=req.available,
            hardware_online=req.hardware_online,
            temperature_c=req.temperature_c,
            knob_factor=req.knob_factor,
            hardware_telemetry=req.hardware_telemetry,
            run_state=req.run_state,
        )
    except KeyError:
        raise HTTPException(404, "unknown pump")
    await broadcast()
    return {"ok": True}


@app.post("/api/hardware/status")
async def update_hardware_status(req: HardwareStatusRequest):
    try:
        res = session.update_hardware_node(
            dev_id=req.dev,
            pump_id=req.pump,
            online=req.online,
            knob=req.knob,
            temperature_c=req.temperature_c,
            light_level=req.light_level,
            telemetry=req.telemetry,
        )
    except KeyError:
        raise HTTPException(404, f"unknown pump {req.pump}")
    await broadcast()
    return {"ok": True, "result": res}


@app.get("/api/hardware/status")
def get_hardware_status():
    return session.get_hardware_summary()


@app.get("/api/assets/{asset_id}/history")
def asset_history(asset_id: str, window_min: int = 240):
    try:
        return session.asset_history(asset_id, window_min)
    except KeyError:
        raise HTTPException(404, "unknown asset")


@app.get("/api/assets/{asset_id}/curves")
def asset_curves(asset_id: str):
    try:
        return session.asset_curves(asset_id)
    except KeyError:
        raise HTTPException(404, "unknown pump")


@app.get("/api/assets/{asset_id}/diagnosis")
def asset_diagnosis(asset_id: str):
    try:
        return session.diagnosis(asset_id)
    except KeyError:
        raise HTTPException(404, "unknown pump")


@app.get("/api/recommendation")
async def get_recommendation():
    run_id, revision = session.run_id, session.revision
    # Capture the immutable simulation inputs before yielding to a worker.
    rec = await asyncio.to_thread(recommend, session.state, session.topo, session.cfg, engine_enabled=session.engine_enabled)
    if run_id == session.run_id and revision == session.revision:
        session.note_advisory(rec)
    return {**rec.model_dump(), "run_id": run_id}


@app.post("/api/recommendation/{option_id:path}/approve")
async def approve(option_id: str, run_id: str):
    if run_id != session.run_id:
        raise HTTPException(409, "Recommendation belongs to an earlier simulation run")
    try:
        session.approve(option_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except KeyError:
        raise HTTPException(404, "unknown option")
    except ValueError as e:
        raise HTTPException(409, str(e))
    await broadcast()
    return {"approved": option_id, "payoff": session.payoff}


@app.post("/api/alarms/{alarm_id}/ack")
async def ack_alarm(alarm_id: str):
    session.ack(alarm_id)
    await broadcast()
    return {"ok": True}


@app.patch("/api/config")
async def patch_config_route(patch: dict):
    try:
        session.patch_config(patch)
    except Exception as e:
        raise HTTPException(400, str(e))
    await broadcast()
    return session.cfg.model_dump()


@app.get("/api/impact/{asset_id}")
def get_impact(asset_id: str):
    try:
        return session.impact(asset_id)
    except KeyError:
        raise HTTPException(404, "unknown asset")


@app.websocket("/ws/sim")
async def ws_sim(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json(session.sync_message())
        while True:
            await ws.receive_text()  # keepalive / detect disconnect
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


@app.get("/api/agent")
async def agent_state():
    return agent.snapshot()


@app.post("/api/agent/enabled")
async def agent_enabled(req: ToggleRequest):
    agent.enabled = req.enabled
    if not req.enabled:
        for task in (agent.chat_task, agent.model_task):
            if task and not task.done():
                task.cancel()
    agent.signature = None
    agent.audit.record(session.run_id, "operator_agent_toggle", {"enabled": req.enabled})
    agent.wake.set()
    return agent.snapshot()


@app.post("/api/agent/chat", status_code=202)
async def agent_chat(req: ChatRequest):
    try:
        return agent.submit_chat(req.message)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/agent/proposals/{proposal_id}/{decision_name}")
async def agent_decision(proposal_id: str, decision_name: str, req: DecisionRequest):
    if decision_name not in ("approve", "reject"):
        raise HTTPException(404, "Unknown decision")
    try:
        result = await agent.decide(proposal_id, decision_name == "approve", req.run_id)
    except KeyError:
        raise HTTPException(404, "Unknown proposal")
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc))
    await broadcast()
    return result


@app.post("/api/agent/scenarios")
async def agent_scenario(req: ScenarioProposal):
    if not agent.enabled:
        raise HTTPException(409, "Agent disabled")
    if agent.lock.locked():
        raise HTTPException(409, "An operator analysis is in progress")
    async with agent.lock:
        ctx = Context(session, agent.audit)
        try:
            result = await asyncio.to_thread(ctx.execute, "submit_scenario_proposal", req.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if not agent.publish_context(ctx):
            raise HTTPException(409, "Scenario changed during analysis")
        return result


@app.get("/api/agent/history")
async def agent_history():
    return await asyncio.to_thread(signals, agent.audit)


@app.post("/api/agent/notes")
async def agent_note(req: NoteRequest):
    if req.asset_id not in session.topo.nodes:
        raise HTTPException(422, "Unknown asset")
    identity = agent.audit.record(session.run_id, "note", {**req.model_dump(), "t_min": session.state.t_min,
                                                         "provenance": "Operator-entered synthetic maintenance observation"})
    if agent.audit.error:
        raise HTTPException(503, "Note could not be stored")
    agent.record_activity("Maintenance note saved", req.asset_id)
    return {"id": identity}
