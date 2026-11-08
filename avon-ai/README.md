# NIGHTWATCH (HackUTD prototype)

Behind every AI model and cloud app is a data center and a team keeping it running around the clock. NIGHTWATCH helps that
team stay one step ahead of **missed warnings**, **unclear handoffs** and **wrong information at the wrong time**.

It is a time-stepped simulation of a synthetic data center cooling plant with layered fault tolerance, predictive alarms,
an advisory decision engine, a shift-handoff brief and a Nemotron-powered investigation team.
**Simulated data. The system never commands equipment; approval is simulated in the UI.**

| Pain point | NIGHTWATCH answer |
| --- | --- |
| A missed warning | Predictive alarms: forecast time-to-limit and an act-by deadline, before any threshold trips |
| An unclear handoff | **Brief** (last 30 min of changes, unacknowledged alarms, next forecast crossing) plus specialist-to-coordinator handoff history |
| Wrong info at the wrong time | Ranked actions with rejection reasons, cited evidence, and a "Simulator rules" label wherever the model fell back |

## Model mapping
Internal field names (`tank`, `pump`, `pipeline`, `volume_bbl`) come from the simulator's original fluid-network model and are kept for stability; the product vocabulary is below.

| Simulator concept | Data center meaning |
| --- | --- |
| Source (`LOAD-A/B`) | Hall IT heat load, kW |
| Tank (`HALL-A/B`) | Hall thermal mass; volume = heat stored above setpoint, kWh. H/HH are temperature limits |
| Buffer tank (`TES-1`) | Thermal energy storage |
| Duty / standby pump (`CHP-1/2/3`) | Chilled-water pump + chiller, duty and N+1 standby |
| Pipeline (`LOOP-A/B`) | Chilled-water loop |
| Treatment (`HRJ-1`) | Shared heat rejection (towers / dry coolers), derated by ambient heat |
| HH interlock | Independent thermal protection that sheds IT load |
| Reduce production | Migrate workloads off a hall |
| Dispatch truck | Deploy a portable chiller (45 min lead time) |

## Run
```
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload          # :8000
cd frontend && npm install && npm run dev        # :5173, proxies /api and /ws to :8000
cd backend && .venv/bin/python -m pytest         # 66 tests
```

## Layers (one sentence each)
1. **Process design** – CHP-1 duty / CHP-2 standby, TES-1 buffer (`data/network.json`).
2. **Basic control** – `control.py` auto-starts the standby after `standby_start_delay_min` on a duty trip (low-flow changeover is a UI toggle, default off).
3. **Alarms** – `alarms.py`: H/HH/L/LL with deadband + on-delay, ack states, plus PREDICTIVE alarms from the forecast.
4. **Operator response** – `decision.py` ranks feasible actions and rejects the rest with reason codes; `POST /api/recommendation/{id}/approve` is the only way advice reaches the sim.
5. **Safety interlock** – `interlock.py` sheds IT load at HH and trips chiller pumps at LL. Shedding is staged: `interlock.shed_ramp_min` (default 3) ramps shed 0→100% on trip and back on reset; set 0 for an instant cut. It imports no decision/forecast/actions code (test enforces it; scene 6 runs with the engine off).
6. **Mitigation** – thermal overflow (runaway) is tracked as the worst outcome in `consequence.py`.

## Hardware Integration (5-Node Visualizer Network)
See [hardware_gateway/README.md](hardware_gateway/README.md) for full setup instructions:
- **Host Computer**: Runs the simulation backend, web dashboard kiosk, `hardware_gateway/bridge.py` (WebSocket to 5x USB Serial), and `hardware_gateway/control_deck.py` (operator controls).
- **Physical Fault Tolerance**: Built-in hot-plug and disconnect resilience in `bridge.py` ensures that if any Arduino is unplugged or fails, the rest of the network and simulation continues completely uninterrupted.
- **5x Arduino UNO R4 WiFi**: PlatformIO firmware driving 12x8 LED matrices across the plant topology:
  1. Tank T-104 & P-203/P-204
  2. Pipeline PL-1 (Upper dynamic waterflow)
  3. Treatment Facility TRT-1 (Intake vortex & backpressure)
  4. Tank T-101 & P-201
  5. Pipeline PL-2 (Lower dynamic waterflow)
- **Protocol & Animation Specs**: Detailed packet definitions in [hardware_gateway/PROTOCOL.md](hardware_gateway/PROTOCOL.md).
- **Test Feeder**: Test any Arduino matrix animation standalone with `py hardware_gateway/tools/test_feeder.py --interactive`.

## Notes / deviations from SPEC
- `SimState.event_log` is replaced by `new_events` (events of the last tick); the session accumulates the log.
- Extra modules: `state.py` (snapshot dataclasses), `session.py` (stateful wrapper), `scenarios.py`, `messages.py` (the only place prose lives).
- Forecasts and recommendations ignore scripted faults that have not started yet.
- Action lead time = intrinsic lead (start delay / ramp / truck 45 min) + `operator_approval_buffer_min`; act-by = time-to-HH minus that.
- Do-nothing cost is derived from the 8 h rollout, so a degraded pump that keeps cycling the HH protection costs several shut-ins (~$24.5k each), not one.
- Pairs are only built from singles that failed on simulation (not hard constraints) – feasible singles dominate any pair containing them.
- Not built: Monte Carlo, lead/lag rotation, REROUTE_TO_BUFFER (the buffer edge is topology only).
- All numbers in `data/config.json` are illustrative. Standards are named only as inspiration.

## NIGHTWATCH Intelligence / Nemotron

The **Agents** tab shows an investigation that starts automatically on a material change. The Thermal Load Monitor reviews tank balance, source rates and discharge restrictions. The Cooling Plant Monitor reviews pump health, flow and standby readiness. Each specialist uses the configured routine model (default Nemotron 3.5 Lightning 30B-A3B). The Coordinator uses the reasoning model (default Nemotron 3.5 Super VL 120B-A12B) and receives both dated reports before briefing the operator. Ask can reference the latest completed investigation. If a role cannot obtain a validated model response, its report is labeled **Simulator rules**.

**Demo:** Load Scene 2 (degraded duty pump), open **Agents → Expand**, and select each monitor to inspect its findings. Open **Handoff history** to see both deliveries before the Coordinator review. Open a source in the Coordinator report to trace it back to a specialist and its simulator readings. No chat message is needed to start the investigation.

Open **NIGHTWATCH Intelligence → Brief** for shift handoff: the last 30 simulated minutes of measured tank volumes, recent changes, alarms needing acknowledgment, and the next forecast high-high crossing. Forecasts show the simulation minute they were calculated. **What-if lab** compares a hypothetical disruption to unchanged conditions at the same minute, showing time to high-high and modeled do-nothing cost. Neither forecast changes playback. In **Ask**, try “What changed this shift?” or investigate an incident with Nemotron. Evidence opens as recorded readings, charts and comparisons; historical source events retain their run and record IDs.

Use **Decision Engine** to rank, inspect and approve feasible actions. Intelligence investigates changes and can propose alternatives for validation; it does not copy the engine’s top action into its proposal queue. The alarm strip above both views shows the highest-priority active alarm and opens the acknowledgment desk.

Copy `backend/.env.example` to `backend/.env` and set `NVIDIA_API_KEY` to connect Nemotron. Start the backend normally; it loads that file automatically. Keys stay on the backend. Model IDs and the OpenAI-compatible base URL are configurable. The defaults use Nemotron 3.5 Lightning and Nemotron 3.5 Super VL; the selected endpoint must support tool calling and JSON output. A real inference call requires a valid provider key and model access.

Without a key, shift handoff, deterministic monitoring, evidence, history, the what-if lab and supported scenario questions remain available. Set `AVON_AGENT_ENABLED=false` to disable the intelligence layer completely, or toggle it in the panel. Playback and safety protection remain independent.

Try scene 2 for pump degradation, scene 3 for standby unavailability, scene 4 for automatic changeover, and scene 5 for correlated treatment restrictions. In Ask, try “Why is HALL-A heating up?”, “What happens if CHP-2 becomes unavailable?”, or “What happens if heat rejection capacity drops by 50%?”. Without Nemotron, only those limited scenario patterns are parsed; broader reasoning requires the configured model.

Proposals enter a central queue, are checked with the same deterministic feasibility/cost evaluator as the ranking engine, and require explicit operator approval. Approval revalidates current state; if playback changes during validation, pause and retry. `EXECUTED_IN_SIM` means scheduled effects were applied, not that a pump ramp or transport cycle has finished. A hypothetical scenario never modifies the playback state. Production-reduction proposals accept integer percentages from 1 to 100; unsupported buffer routing is rejected.

Agent requests, tool results, evidence, proposals, decisions, events, and operator-entered synthetic maintenance notes are retained in `data/agent/audit.sqlite3` (ignored by Git). Historical counts are observations from retained simulation events, not reliability probabilities. Model prose is presented as cited qualitative interpretation; displayed quantities come from simulator evidence. If the audit store is unavailable, the panel reports it while simulation continues.

Agent endpoints: `GET /api/agent`, `POST /api/agent/chat`, `POST /api/agent/enabled`, `POST /api/agent/scenarios`, `POST /api/agent/proposals/{id}/{approve|reject}`, `GET /api/agent/history`, and `POST /api/agent/notes`. The approval body contains the displayed `run_id` to reject decisions from previous runs.
