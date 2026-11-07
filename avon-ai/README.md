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
- Not built (marked `TODO(phase3)`): LLM layer, Monte Carlo, lead/lag rotation, REROUTE_TO_BUFFER.
- All numbers in `data/config.json` are illustrative. Standards are named only as inspiration.
