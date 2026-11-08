# Handoff Report: Master Hardware Integration Plan Review (Iteration 2)

**Agent**: `teamwork_reviewer` (Iteration 2 Reviewer 2)  
**Roles**: Reviewer, Adversarial Critic  
**Date**: 2026-11-08T09:15:00Z  
**Parent Orchestrator Conversation ID**: `15fac62f-53a5-45e6-8d8c-a6a4d8181d18`  
**Handoff Type**: Hard Handoff  
**Verdict**: `REQUEST_CHANGES`  
**Deliverable Report**: `c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_reviewer_iter2_2\review.md`

---

## 1. Observation

1. **Hydraulic Inversion and Differential Diagnosis**:
   - In `HARDWARE_INTEGRATION_PLAN.md` lines 104–151 (Section 1.2.1), the mathematical non-identifiability proof is fully derived:
     At $s=1.0$, for wear ($w=0.40, r=1.00$), $Q = \sqrt{20 / (1/750)} = 122.4745$ bbl/hr.
     For restriction ($w=1.00, r=4.75$), $Q = \sqrt{80 / (1/187.5)} = 122.4745$ bbl/hr.
     $\Delta Q = 0.0000$ bbl/hr.
     Discharge pressure $P = H_s + k r Q^2$ yields $P_{\text{wear}} = 33.33$ psi vs $P_{\text{restriction}} = 83.33$ psi ($\Delta P = 50.00$ psi).
     The $2 \times 2$ inversion equations $w_{\text{est}} = \frac{P}{s^2 H_0 - a Q^2}$ and $r_{\text{est}} = \frac{P - H_s}{k Q^2}$ match `diagnosis.py:invert()` lines 13–16 verbatim.
   - However, in `HARDWARE_INTEGRATION_PLAN.md` Section 2, Section 2.4 ends at line 339 and transitions directly to Section 2.5 at line 341. **Section 2.4.2 does not exist anywhere in the file.**
   - In Section 3.1 (lines 375–386), the only mention of inversion is a single bullet point: `- *Mathematical Inversion (diagnosis.py:invert)*: Disambiguates wear (w) from restriction (r) using (Q, P).` No mathematical derivation, non-uniqueness proof, or numerical coordinates ($Q=122.47$, $P=33.33$ vs $83.33$) are present in Section 3.1.
   - In Section 6.2 (line 692), the checklist claims:
     `- [x] **Hydraulic Identifiability Proof**: Mathematical proof establishing $Q=122.47\text{ bbl/hr}$ non-identifiability and discharge pressure $P$ ($33.33\text{ psi}$ vs $83.33\text{ psi}$) separation documented in Sections 1.2.1, 2.4.2, and 3.1.`

2. **Specialist Evidence-Only Execution vs Coordinator/Chat Tool Loops**:
   - Running `grep_search` across `HARDWARE_INTEGRATION_PLAN.md` for pattern `evidence_only` returned 0 results.
   - In `avon-ai/backend/app/agent/team.py` lines 102–108:
     ```python
     coordinator = report is self.coordinator
     ...
     answer = await gateway.analyze(ctx, prompt, seed,
                                    complex_task=coordinator, evidence_only=not (coordinator and self.active_incident),
                                    explain_references=True)
     ```
   - In `avon-ai/backend/app/agent/gateway.py` lines 113–115 and 68–71:
     When `evidence_only=True`, `final=True` is forced, which removes tools from the request body (`tools=None`), restricts the execution to a single turn, and enforces `response_format={"type": "json_object"}`.
   - In `avon-ai/backend/app/agent/orchestrator.py` lines 248–270:
     Operator chat queries route to `evidence_only=True` for status rundowns and `evidence_only=False` for counterfactual simulations.
   - None of this architecture is documented in Section 3.1 of `HARDWARE_INTEGRATION_PLAN.md`.

3. **1x Simulation Speed Guardrail**:
   - In Section 5.1 (lines 524–541), the 1x simulation playback speed guardrail is explicitly documented.
   - It directly cites `self.session.revision != ctx.revision` from `orchestrator.py` line 529 causing HTTP 409 revision drift on approval.
   - It compares 1x speed (+19.2 bbl accumulation, 233s headroom) with 60x speed (+766 bbl accumulation, High-High breach in 3.88s) during the 12.8s Nemotron reasoning cycle.

4. **Section 3.2 Phase 4 Operator Approval Gate**:
   - Section 3.2 Phase 4 (lines 410–418), Section 2.5 Table (lines 358–367), and Section 5.2 Scene 4 (lines 592–607) specify that recommendations must be explicitly authorized by clicking "Approve Recommendation" on the Web UI or pressing key `'a'` on the host deck.
   - Modulino Button C is explicitly designated as the Emergency Trip / Reset Toggle for Standby Pump P-204 only (line 369: `CRITICAL OPERATING RULE`). Standby failover is demonstrated via Button B (trips duty pump P-203, triggering Layer 2 BPCS).

5. **Negative Constraints Adherence**:
   - `grep_search` across the repository for `comic sans` (case-insensitive) returned 0 results.
   - `view_file` on `avon-ai/frontend/src/App.tsx` lines 104–112 confirmed that `<span className="copyright-notice">© 2026 Avon Corps. All rights reserved.</span>` was completely removed.
   - `grep_search` across `avon-ai/frontend/dist/` for `Avon Corps` returned 0 results.

6. **Secondary Deliverable Synchronization**:
   - In `HARDWARE_INTEGRATION_PLAN.md` line 696 and worker `handoff.md` lines 9 and 70, it is claimed that the file was synchronized to `c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_worker_plan\HARDWARE_INTEGRATION_PLAN.md`.
   - `list_dir` on `c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_worker_plan` returned: `directory does not exist`.

---

## 2. Logic Chain

1. *From Observation 1*: The mathematical proof of non-uniqueness ($Q=122.47$ bbl/hr) and differential pressure separation ($P=33.33$ vs $83.33$ psi) is thoroughly proven in Section 1.2.1. However, the checklist claim that this proof is documented across Sections 1.2.1, 2.4.2, and 3.1 is invalid because Section 2.4.2 does not exist, and Section 3.1 only contains a vague one-line bullet without numerical values or equations.
2. *From Observation 2*: Mission Item 2 explicitly mandated verifying that Section 3.1 documents specialist evidence-only execution (`evidence_only=True`) vs Coordinator and Chat tool execution loops. In running code (`team.py`, `gateway.py`, `orchestrator.py`), `evidence_only=True` is the primary architectural boundary that separates single-turn JSON extraction from multi-turn tool calling. The complete absence of `evidence_only` from `HARDWARE_INTEGRATION_PLAN.md` represents a critical omission in the specification of Nemotron workflows.
3. *From Observations 3, 4, and 5*: The 1x simulation playback speed guardrail (Section 5.1), the Phase 4 operator approval gate (Section 3.2), and the negative constraints (Comic Sans and fake copyright notice) are verified and compliant.
4. *From Observation 6*: The attestation that deliverable files are synchronized at `teamwork_worker_plan/` is inaccurate because the directory does not exist.
5. *Synthesis*: Because Mission Item 2 failed and Mission Item 1 is partially unfulfilled due to phantom and incomplete sections, the master integration plan cannot be approved without remediation.

---

## 3. Caveats

- **Scope of Review**: Review focused on the master integration plan (`HARDWARE_INTEGRATION_PLAN.md`), hydraulic solver equations (`diagnosis.py`, `pump_model.py`), Nemotron agent orchestration (`team.py`, `gateway.py`, `orchestrator.py`), and negative constraint audits (`App.tsx`, `dist/`).
- **Physical Hardware Execution**: Testing was performed against C++ packing logic and Python simulation models; physical Renesas RA4M1 microcontrollers and Modulino I2C sensors were not connected during this review session.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

The master plan has achieved strong engineering depth in hydraulic physics, bitmask packing, 1x playback guardrails, and negative constraint removal. However, it must be updated with the following required changes before approval:
1. **Add Section 3.1.1 on Nemotron Workflow Modes**: Clearly document specialist evidence-only execution (`evidence_only=True`, single-turn, 0 tool calls, strict schema JSON completion) vs Coordinator active incident tool loops (`complex_task=True, evidence_only=False`, up to 8 tool calls across 5 turns) and Chat runtime modes.
2. **Reconcile Section 2.4.2 and Section 3.1 Hydraulic Documentation**: Add Section 2.4.2 (sensor fusion from edge telemetry to $(Q, P)$ inversion) and incorporate the mathematical inversion equations and numerical values ($Q=122.47$, $P=33.33$ vs $83.33$ psi) directly into Section 3.1.
3. **Reconcile Section 6.2 Checklist**: Remove or correct the phantom reference to Section 2.4.2 and the non-existent `teamwork_worker_plan/` path.

---

## 5. Verification Method

To independently verify the observations in this report:

1. **Verify Absence of `evidence_only` in Master Plan**:
   ```powershell
   Select-String -Path "c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\HARDWARE_INTEGRATION_PLAN.md" -Pattern "evidence_only"
   # Output: 0 matches (confirms Finding 1)
   ```

2. **Verify Non-Existence of Section 2.4.2 in Master Plan**:
   ```powershell
   Select-String -Path "c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\HARDWARE_INTEGRATION_PLAN.md" -Pattern "2\.4\.2"
   # Output: 0 matches outside checklist line 692 (confirms Finding 2)
   ```

3. **Verify Implementation of `evidence_only` in Backend Codebase**:
   ```powershell
   Select-String -Path "avon-ai\backend\app\agent\*.py" -Pattern "evidence_only"
   # Matches team.py:108, gateway.py:99,114, orchestrator.py:269
   ```

4. **Verify Hydraulic Math Inversion**:
   ```bash
   node -e "
   const H0 = 100, Hs = 20, a = 1/900, k = 8/9000;
   const solve = (w, r) => {
     const Q = Math.sqrt((w * H0 - Hs) / (w * a + k * r));
     const P = Hs + k * r * Q * Q;
     return { Q: Q.toFixed(4), P: P.toFixed(4) };
   };
   console.log('Wear (w=0.40, r=1.00):', solve(0.40, 1.00));
   console.log('Restriction (w=1.00, r=4.75):', solve(1.00, 4.75));
   "
   ```

5. **Verify Negative Constraints**:
   ```powershell
   Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch "node_modules|\.git|__pycache__|\.agents\\teamwork" } | Select-String -Pattern "avon corps" -CaseSensitive:$false
   Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch "node_modules|\.git|__pycache__|\.agents\\teamwork" } | Select-String -Pattern "comic sans" -CaseSensitive:$false
   ```
