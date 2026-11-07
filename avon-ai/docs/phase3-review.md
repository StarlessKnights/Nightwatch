# Phase 3 repository review and proposed implementation

Reviewed: 2026-11-07. This is a design review, not an implemented feature. Obtain the operator's approval before implementing each main feature, as requested. No feature commit or push is authorized by this review.

## Current system

The repository is a synthetic produced-water network simulator. Its existing “AVON AI” recommendations are deterministic; there is no model integration, autonomous agent, conversational interface, or persistent incident store.

The topology contains 11 assets: two sources, three tanks, three pumps, two pipelines, and one shared treatment facility. SRC-1 feeds T-104 through duty P-203 / standby P-204 and PL-1; SRC-2 feeds T-101 through P-201 and PL-2. Both pipelines terminate at TRT-1. T-102 is a buffer connected to T-101 by a transfer edge. That edge participates in impact tracing but does not transfer liquid in the physics engine.

The default simulation step is one minute; the forecast horizon is 480 minutes. Playback supports 1, 10, and 60 simulated minutes per real second. All configured costs and limits are illustrative.

### Backend map

| Module | Responsibility and reuse opportunity |
| --- | --- |
| `backend/app/main.py` | FastAPI routes, application lifespan, global session, playback loop, WebSocket broadcasting. Appropriate composition point for an optional agent service. |
| `session.py` | Owns current state/configuration, RNG, event history, forecasts, commands, and approval. Boundary for observation snapshots and operator commands. |
| `state.py` | Frozen dataclasses for simulation state, faults, alarms, events, pending actions. Nested dictionaries are still mutable: frozen does not mean deeply immutable. |
| `models.py` | Pydantic configuration, API requests, forecast, cause, cost, option, and recommendation contracts. Reuse these deterministic output contracts. |
| `sim.py` | State transition: due actions and faults → sensors → interlocks → control → flow allocation → integration → alarms. Keep independent of the agent. |
| `interlock.py` | HH source shut-in and LL pump protection with reset hysteresis; independent of the decision engine. |
| `control.py` | Duty restart, standby changeover, optional low-flow changeover, automatic standby stop. |
| `flow.py` | Proportional allocation under shared pipeline/treatment caps and available tank volume. |
| `forecast.py` | Rolls forward the same simulator; derives trajectories and time-to-limit. Excludes scripted faults that have not started. |
| `decision.py` | Generates actions, checks hard constraints, simulates feasible candidates, calculates costs, and ranks. Also emits probable causes and affected assets. |
| `actions.py` | Standby start, production reduction, truck dispatch, action pairs, preconditions, lead times, scheduling, and effects. |
| `consequence.py` | Derived production-loss, shut-in, and overflow costs. Authoritative source for financial comparisons. |
| `network.py` | Topology loading, equipment relationships, cached upstream/downstream BFS traversal. |
| `faults.py` | Seven fault types, base/effective equipment views, sensor faults, injection and removal. |
| `alarms.py` | Process/system/predictive alarm state machines, on-delay, deadband, acknowledgement. |
| `scenarios.py` | Seven replayable JSON scenarios and initial state construction. |
| `messages.py` | Deterministic human-readable event, rejection, and headline templates. Useful fallback material. |

`Session.approve()` recalculates a recommendation, checks feasibility, and schedules its action(s). This already provides a valuable approval-time validation boundary. `forecast.rollout()` schedules hypothetical actions on a copied state without changing the live session.

### Existing API surface

| Interface | Behavior |
| --- | --- |
| `GET /api/network` | Topology, configuration, fault catalog, scenario metadata, full snapshot. |
| `GET /api/scenarios` | Available scripted scenarios. |
| `GET /api/recommendation` | Calculates ranked/rejected options; also logs a changed advisory. It is not strictly side-effect-free. |
| `GET /api/impact/{asset_id}` | Graph upstream/downstream assets and a first-to-limit field. |
| `WS /ws/sim` | Initial/full `sync` and incremental `tick` envelopes, state, forecasts, history, and events. |
| `POST /api/sim/{start,pause,step,reset,speed,engine}` | Playback and deterministic-engine controls. |
| `POST /api/scenarios/{scenario_id}/load` | Replaces the current session scenario. |
| `POST /api/faults`, `DELETE /api/faults/{fault_id}` | Mutate simulated faults. |
| `PATCH /api/assets/{asset_id}`, `PATCH /api/config` | Mutate equipment availability/capacity and configuration. |
| `POST /api/recommendation/{option_id}/approve` | Revalidates and schedules simulated actions. |
| `POST /api/alarms/{alarm_id}/ack` | Operator acknowledgement. |

The proposed agent's read tools mostly need adapters, not additional physics. There is no standalone scenario-results API, persistent event-history API, proposal queue, reject endpoint, or maintenance-note store yet. Never give the model access to the mutation routes above.

### Frontend map

`useSim.ts` fetches the initial network, consumes/reconnects the WebSocket, retains bounded history, and throttles recommendation requests to 1.5 seconds. `api.ts` wraps REST calls; `types.ts` mirrors backend contracts, with many asset/configuration fields currently typed as generic dictionaries.

`App.tsx` composes the fault drawer, React Flow network, recommendations/alarms column, tank trends, and event log. `NetworkDiagram.tsx` already highlights related assets on a node click. `Recommendations.tsx` shows deterministic rankings, rejection reasons, costs, and approval. `TankTrends.tsx` overlays history, baseline forecasts, and selected-action trajectories. `EventLog.tsx` already distinguishes AUTO, ADVISORY, OPERATOR, FAULT, ALARM, and SYSTEM. `FaultPanel.tsx`, `TransportBar.tsx`, `AlarmList.tsx`, and `PayoffBanner.tsx` complete the operator workflow.

Extend these components with an Intelligence panel and an evidence viewer. Preserve the deterministic recommendation panel and its ranking. Add an origin field within ADVISORY so deterministic recommendations and model proposals remain distinguishable.

## Integration findings

These observations are based on source inspection unless a runtime reproduction is stated in the verification section.

1. **Proposal evaluation needs a public deterministic boundary.** `decision.recommend()` defines `evaluate(combo)` as a nested function. Extract that logic into a shared deterministic service before accepting model-generated alternatives; do not duplicate its calculations in agent code. Existing approval only recognizes options regenerated by the recommendation engine, so arbitrary new combinations cannot simply be passed to that route.
2. **The action library is narrower than the product vision.** Production reductions are generated at 10%, 25%, and 50%; combinations are capped at pairs and only sampled from singles rejected by simulation rather than hard constraints. Buffer routing is not implemented. The first proposal implementation should stay inside the supported action vocabulary and configured values; finer percentages, additional combinations, and transfer physics require explicit scope decisions.
3. **There is no internal event subscription mechanism.** `tick_message()` consumes pending WebSocket deltas, and `sync_message()` also clears those deltas. An agent must not consume that same queue. Introduce an independent observer cursor/queue at the session/application boundary, including events produced while playback is paused and scenario initialization. Monitoring must work with no browser connected.
4. **Forecast freshness needs explicit versioning.** Forecasts are periodically refreshed, but `_envelope()` labels the cached forecast with the current state minute. Record the actual calculation minute and input revision. A state snapshot, forecast, recommendation, and model reply must retain their own provenance.
5. **Session identity must survive asynchronous work.** Scenario load/reset clears the log and resets event IDs. Add a run ID and a monotonically increasing state/configuration revision. Reject late replies and invalidate proposals from previous runs. Minute alone is insufficient because faults and configuration can change while paused.
6. **Validation must become stricter before model inputs are accepted.** `faults.validate()` checks fault type and target kind, then merges parameters without enforcing numeric bounds, enum membership, unknown keys, finiteness, or fault duration. Model proposals require strict Pydantic schemas plus deterministic asset/type/catalog validation. Do not expose raw `Action` construction or ID parsing as the trust boundary.
7. **Graph reachability is not a proven operational effect.** Transfer edges are included in BFS despite missing transfer physics. Shared-treatment competition can also affect a sibling branch that a simple upstream/downstream walk from a pump does not enumerate. Include shared capacity consumers in relevant context and use rollouts to establish consequences. `Session.impact()` currently chooses first-to-limit globally, not only among the selected asset's affected tanks.
8. **Observation must not reveal future scripted incidents.** `state_dict()` includes scheduled future faults for the fault-injection UI; forecasts correctly filter them out. Agent adapters must filter future script entries and avoid scenario descriptions that disclose them. Operator-requested what-if changes should be separately identified as hypothetical.
9. **Model work must be outside the playback path.** The current loop synchronously advances state and refreshes forecasts; approval also performs synchronous recommendation calculations. Model calls and added rollouts need bounded workers, copied inputs, timeouts, and cancellation. A stale response must not overwrite newer evidence. Workers must never mutate the live session.
10. **History is currently temporary.** Events retain only the latest 2,000 rows and reset on scenario load; tank history retains 720 points by default. Historical intelligence and audit require a separate durable store with source IDs, run IDs, timestamps, and retained evidence snapshots.
11. **Approval and execution need separate tracking.** There is no proposal lifecycle or duplicate-approval guard. An action may be scheduled, become effective, or be skipped; trucks also have later load events. Record these outcomes explicitly and do not mark a proposal executed merely because the operator clicked Approve. Revalidate current feasibility and atomically consume the approval transition.
12. **Frontend responses can arrive out of order.** Recommendation fetches are throttled but not guarded by run/revision or cancelled on scenario changes. Apply revision checks to future agent messages and existing recommendations when integrating the panel. Configuration fetched initially is also not refreshed as a complete object after patches.

Other existing assumptions to retain visibly: global tank thresholds, deterministic point forecasts rather than calibrated probabilities, illustrative cost coefficients, and a single in-memory session shared by all clients. Configuration patches persist through scenario loads because overrides merge into the current configuration. This deserves a deliberate reset policy before reproducibility claims span multiple scenarios.

## Proposed agent architecture

Keep `backend/app/agent/` separate. `main.py` composes an optional agent runtime with a narrow observation adapter. `interlock.py`, `control.py`, `flow.py`, and `sim.py` must never import the agent, including indirectly through new provider dependencies.

```text
Session observations + actual forecast/recommendation revisions
    -> bounded deterministic monitor and incident grouping
    -> filtered evidence package
    -> configurable Nemotron gateway and bounded tool loop
    -> strict structured response / proposal
    -> shared deterministic validation and sandbox rollout
    -> evidence-backed briefing / validated advisory
    -> operator approval + current-state revalidation
    -> existing simulated action scheduling and outcome events
```

Use the requested gateway, monitor, orchestrator, tools, proposals, incidents, critic, history, and audit modules as their milestones arrive. Add settings and API adapters where needed. A new orchestration framework is not necessary for the initial bounded workflow; `httpx`, Pydantic, and asyncio are already available.

**Read tools:** return copied, typed, versioned data for network/asset state, forecasts, impact, deterministic recommendations, alarms, history, and stored scenario results. Build `get_recommendations()` around a captured snapshot and the pure engine rather than the GET route's advisory side effect. Do not give tools a mutable `Session` object.

**Proposal tools:** permit only typed action-library proposals, fault hypotheses, and sandbox scenarios. A hypothesis is a claim to investigate, not an injected live fault. A scenario clones inputs, applies validated hypothetical faults, and calls the existing rollout/recommendation services. Historical reliability estimates remain annotated estimates and cannot automatically change simulation parameters.

**Evidence:** represent factual claims as references to server-owned evidence records containing run/revision, source/tool, simulator path or event ID, exact observed value, units, and observation minute. Numeric benefits come from stored deterministic results. Reject unknown/mismatched citations; render quantitative assertions from verified fields instead of trusting arbitrary model prose. Label causal interpretation as a hypothesis unless established by the simulator. A clickable citation alone does not prove the attached prose is true.

**Queue:** preserve PENDING → VALIDATED/REJECTED → APPROVED → EXECUTED_IN_SIM. Store rejection reasons, validation revision, operator decisions, and simulator outcomes. Revalidate after material state changes and at approval. Expiry, operator rejection, and skipped execution need explicit reason/outcome fields; never silently schedule from a model tool call. The queue belongs outside the authoritative physics modules.

**Efficiency:** deterministic event filtering, severity thresholds, short correlation windows, and periodic local checks precede any model request. Deduplicate by run, cause/asset cluster, and incident state; update an existing incident on meaningful severity/evidence changes. Cache by relevant state/configuration revision, not just event text. Bound queued work, context size, tool calls, model tokens, and request rate. Critical conditions receive immediate deterministic briefings even if the model is slow or unavailable.

**Failure handling:** disabled mode must create no provider dependency or requests. Timeouts, invalid JSON, unsupported tools, provider errors, audit failures, and worker crashes cannot stop playback or interlocks. Surface degraded agent status and deterministic fallback summaries. Audit requests, final responses, tool calls, validation, and operator decisions with secrets redacted; visible activity should report operations and concise conclusions rather than private model reasoning.

## Nemotron selection

Research date: 2026-11-07. The following is a proposed evaluation baseline, not a claim of measured AVON performance.

| Role | Proposed model | Rationale |
| --- | --- | --- |
| Routine classification and concise briefings | `nvidia/nemotron-3.5-lightning-30b-a3b` on NVIDIA; provider-specific ID configurable | NVIDIA describes a 30B-total/3B-active hybrid MoE model for high-throughput agent workflows. [NVIDIA model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard). |
| Complex incidents, competing alternatives, critic | `nvidia/nemotron-3.5-super-vl-120b-a12b` on NVIDIA; provider-specific ID configurable | Candidate reasoning tier with 120B total/12B active parameters and tool use. Text-only AVON inputs do not require using its vision capabilities. [NVIDIA model card](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b/modelcard). |

Start with a hosted endpoint to avoid requiring local GPU infrastructure. Use configurable base URL, API key environment-variable name, routine/reasoning model IDs, capabilities, timeouts, and token budgets. NVIDIA-hosted access is the prototype target; retain an adapter for paid hosted providers or self-hosted NIM/vLLM. Access, quotas, and exact hosted feature support still require an authenticated smoke test. [Lightning API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b), [Super VL API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b).

NVIDIA's Lightning NIM guide documents tool calling and `response_format` JSON mode with client-side Pydantic validation. It documents parser configuration and warns that reasoning can consume the token budget before JSON finishes. Treat JSON-schema enforcement as an endpoint capability, not a universal property of every compatible API; keep separate tool and final-structured-output stages if needed. [NIM deployment and request guide](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3.5-lightning.html).

For self-hosting, NVIDIA's Lightning NIM support matrix lists single-GPU minimums of 30 GB for NVFP4 on Blackwell, 32 GB for W4A16 on Ampere or newer, and 66 GB for BF16; long contexts and concurrency need additional headroom. These are NIM profile requirements, not universal minima for every inference implementation. Super VL lists Hopper/Blackwell platforms and Linux; determine its actual GPU count from the selected runtime/profile rather than its active-parameter count. [NIM support matrix](https://docs.nvidia.com/nim/large-language-models/2.0.10/reference/support-matrix.html), [Super VL hardware information](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b/modelcard).

For a concrete paid-hosting comparison, OpenRouter's DeepInfra rows currently list Lightning at $0.06 per million input tokens / $0.16 output, and Super VL at $0.15 / $0.50. A hypothetical 2,000-input/500-output-token request is therefore approximately $0.00020 or $0.00055 respectively, before retries, extra reasoning/tool turns, fees, or discounts. These are arithmetic estimates from listed token prices, not NVIDIA endpoint pricing or measured AVON request costs. The same provider rows report latency of about 0.38 seconds versus 0.94 seconds and throughput of 205 versus 160 tokens/second; they are provider observations, not end-to-end incident response guarantees. [Lightning pricing/provider rows](https://openrouter.ai/nvidia/nemotron-3.5-lightning), [Super VL pricing/provider rows](https://openrouter.ai/nvidia/nemotron-3.5-super-vl).

Before choosing final defaults, measure JSON validity, valid tool arguments, evidence correctness, scenario answer quality, p50/p95 completion latency, token usage, and cost per consolidated incident. Generic benchmarks do not establish AVON-specific tool reliability. Use the seven existing scenarios plus malformed-output, provider-failure, stale-result, and conflicting-action cases.

## Incremental implementation and approval gates

| Milestone | Concrete deliverable | Evidence required before completion |
| --- | --- | --- |
| 1. Gateway | Isolated settings/provider interface, Nemotron transport, strict output/tool envelopes, bounded retries/timeouts, fallback, audit foundation, opt-in connection probe. | Mocked valid/invalid outputs; timeout, rate limit, server/auth errors; disabled mode; no secret leakage; authenticated probe when credentials are configured. |
| 2. Monitoring | Independent event observations, run/revision tracking, actual forecast timestamps, bounded queue, significant-change detection and deduplication. | Detect scripted/manual changes without an operator prompt or browser; no model call for unchanged checks; reset/paused/speed handling. |
| 3. Briefings | Correlated incidents, graph/shared-resource context, verified evidence, deterministic fallback, Intelligence panel/feed/activity, graph highlights. | One incident for related alarms; separate unrelated incidents; clickable evidence; automatic protections distinguished from pending attention. |
| 4. Recommendations | Shared deterministic evaluator, strict proposals, central queue, operator approve/reject, revalidation and simulator outcome tracking. | Reject unavailable/late/conflicting actions; no live-state effects from proposals; unchanged original ranking; duplicate/stale approval protection. |
| 5. Operator interaction | Bounded read/proposal tool loop, evidence-backed questions and sandbox what-if analysis, missing-information prompts. | Explain T-104 filling and compare P-204 unavailability / 50% treatment loss using recorded tool results; live state unchanged. |
| 6. History and critic | Durable event/note provenance, explicitly estimated reliability signals, recommendation critique, post-incident reports. | Trace historical claims to source text/events; no inferred reliability injected into calculations; critique cannot change ranking. |

Across milestones, enforce import-independence and playback/safety equivalence with the agent disabled, unavailable, and returning invalid output. The existing interlock test only checks selected direct imports; extend that boundary to all four protected modules and relevant transitive dependencies.

### First feature submitted for approval

Implement **Priority 1 only: the Nemotron gateway foundation**. Proposed additions: `agent/__init__.py`, `agent/settings.py`, `agent/gateway.py`, structured response/tool schemas, `agent/audit.py`, focused gateway tests, environment-variable documentation, and an opt-in synthetic connection probe. Use the existing `httpx` dependency.

The feature is complete when disabled mode needs no credentials, mocked tool and structured responses validate correctly, failures return typed fallback results within bounded deadlines, and audit output redacts credentials. An authenticated endpoint test must be reported separately if no key is configured. Live monitoring, proposal execution workflow, and the panel follow under their own approvals.

## Verification

All application source, test files, seven scenario definitions, configuration, topology, frontend components/styles, build configuration, and dependency manifests were reviewed. Dependency lock metadata was inspected.

- Backend: `python -B -m pytest -p no:cacheprovider` passed all 27 tests in 19.89 seconds using Python 3.13.15 and a local virtual environment installed from the declared requirements.
- Frontend: `npm run build` passed TypeScript compilation and the Vite production build. Vite reported the existing bundle-size warning (largest JavaScript chunk approximately 779 kB before gzip).
- Frontend: `npm run lint` exited successfully with one existing `react(set-state-in-effect)` warning at `NetworkDiagram.tsx:107`.
- Isolated FastAPI TestClient smoke test passed network retrieval, scenario load, recommendation, operator approval, and WebSocket sync. Scene 2 selected `START_STANDBY_PUMP:P-204`; the deterministic action cost returned by approval was $248.75.
- Runtime reproduction confirmed stale forecast provenance: after advancing scene 2 from minute 0 to minute 1 without a forecast refresh, the cached series still started at 880 bbl, the current tank was 881.5 bbl, and the envelope labelled that forecast as minute 1.
- Runtime reproduction confirmed that `faults.validate()` accepts pump degradation `factor=2`, outside the catalog's 0.1–0.95 range.
- Runtime reproduction confirmed that P-201 impact reports T-104 as first-to-limit even though its returned upstream/downstream lists exclude T-104.
- No browser visual review or authenticated Nemotron inference test was performed. Model latency, quality, cost, and endpoint compatibility remain evaluation work, not verified application behavior.

Application source and dependency manifests were left unchanged. Local verification generated the backend virtual environment, frontend dependencies, and ignored build artifacts. The only new project content is this review document.
