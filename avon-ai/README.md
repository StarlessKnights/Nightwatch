# AVON AI (hackathon prototype)

Time-stepped simulation of a synthetic produced-water network with layered fault tolerance and an
advisory decision engine. **Simulated data. The system never commands equipment; approval is simulated in the UI.**

## Run
```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload          # :8000
cd frontend && npm install && npm run dev        # :5173, proxies /api and /ws to :8000
cd backend && .venv/bin/python -m pytest         # 27 tests
```

## Layers (one sentence each)
1. **Process design** – P-203 duty / P-204 standby, T-102 buffer (`data/network.json`).
2. **Basic control** – `control.py` auto-starts the standby after `standby_start_delay_min` on a duty trip (low-flow changeover is a UI toggle, default off).
3. **Alarms** – `alarms.py`: H/HH/L/LL with deadband + on-delay, ack states, plus PREDICTIVE alarms from the forecast.
4. **Operator response** – `decision.py` ranks feasible actions and rejects the rest with reason codes; `POST /api/recommendation/{id}/approve` is the only way advice reaches the sim.
5. **Safety interlock** – `interlock.py` shuts in inflow at HH and trips pumps at LL. It imports no decision/forecast/actions code (test enforces it; scene 6 runs with the engine off).
6. **Mitigation** – overflow is tracked as the worst outcome in `consequence.py`.

## Notes / deviations from SPEC
- `SimState.event_log` is replaced by `new_events` (events of the last tick); the session accumulates the log.
- Extra modules: `state.py` (snapshot dataclasses), `session.py` (stateful wrapper), `scenarios.py`, `messages.py` (the only place prose lives).
- Forecasts and recommendations ignore scripted faults that have not started yet.
- Action lead time = intrinsic lead (start delay / ramp / truck 45 min) + `operator_approval_buffer_min`; act-by = time-to-HH minus that.
- Do-nothing cost is derived from the 8 h rollout, so a degraded pump that keeps cycling the HH interlock costs several shut-ins (~$24.5k each), not one.
- Pairs are only built from singles that failed on simulation (not hard constraints) – feasible singles dominate any pair containing them.
- Not built: Monte Carlo, lead/lag rotation, REROUTE_TO_BUFFER (the buffer edge is topology only).
- All numbers in `data/config.json` are illustrative. Standards are named only as inspiration.

## AVON Intelligence / Nemotron

Open **AVON Intelligence → Brief** for shift handoff: the last 30 simulated minutes of measured tank volumes, recent changes, alarms needing acknowledgment, and the next forecast high-high crossing. Forecasts show the simulation minute they were calculated. **What-if lab** compares a hypothetical disruption to unchanged conditions at the same minute, showing time to high-high and modeled do-nothing cost. Neither forecast changes playback. In **Ask**, try “What changed this shift?” or investigate an incident with Nemotron. Evidence opens as recorded readings, charts and comparisons; historical source events retain their run and record IDs.

Use **Decision Engine** to rank, inspect and approve feasible actions. Intelligence investigates changes and can propose alternatives for validation; it does not copy the engine’s top action into its proposal queue. The alarm strip above both views shows the highest-priority active alarm and opens the acknowledgment desk.

Copy `backend/.env.example` to `backend/.env` and set `NVIDIA_API_KEY` to connect Nemotron. Start the backend normally; it loads that file automatically. Keys stay on the backend. Model IDs and the OpenAI-compatible base URL are configurable. The defaults use Nemotron 3.5 Lightning and Nemotron 3.5 Super VL; the selected endpoint must support tool calling and JSON output. A real inference call requires a valid provider key and model access.

Without a key, shift handoff, deterministic monitoring, evidence, history, the what-if lab and supported scenario questions remain available. Set `AVON_AGENT_ENABLED=false` to disable the intelligence layer completely, or toggle it in the panel. Playback and safety protection remain independent.

Try scene 2 for pump degradation, scene 3 for standby unavailability, scene 4 for automatic changeover, and scene 5 for correlated treatment restrictions. In Ask, try “Why is T-104 filling up?”, “What happens if P-204 becomes unavailable?”, or “What happens if treatment capacity drops by 50%?”. Without Nemotron, only those limited scenario patterns are parsed; broader reasoning requires the configured model.

Proposals enter a central queue, are checked with the same deterministic feasibility/cost evaluator as the ranking engine, and require explicit operator approval. Approval revalidates current state; if playback changes during validation, pause and retry. `EXECUTED_IN_SIM` means scheduled effects were applied, not that a pump ramp or transport cycle has finished. A hypothetical scenario never modifies the playback state. Production-reduction proposals accept integer percentages from 1 to 100; unsupported buffer routing is rejected.

Agent requests, tool results, evidence, proposals, decisions, events, and operator-entered synthetic maintenance notes are retained in `data/agent/audit.sqlite3` (ignored by Git). Historical counts are observations from retained simulation events, not reliability probabilities. Model prose is presented as cited qualitative interpretation; displayed quantities come from simulator evidence. If the audit store is unavailable, the panel reports it while simulation continues.

Agent endpoints: `GET /api/agent`, `POST /api/agent/chat`, `POST /api/agent/enabled`, `POST /api/agent/scenarios`, `POST /api/agent/proposals/{id}/{approve|reject}`, `GET /api/agent/history`, and `POST /api/agent/notes`. The approval body contains the displayed `run_id` to reject decisions from previous runs.
