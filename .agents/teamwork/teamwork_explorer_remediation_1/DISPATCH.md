## 2026-11-08T08:33:42Z
You are teamwork_explorer (Remediation Explorer).
Your working directory is: c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_explorer_remediation_1\
Parent orchestrator conversation ID: 15fac62f-53a5-45e6-8d8c-a6a4d8181d18

Read ORIGINAL_REQUEST.md first:
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\ORIGINAL_REQUEST.md

Read PROJECT.md:
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\PROJECT.md

Read DEAD_ENDS.md:
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\orchestrator_1\DEAD_ENDS.md

Read the Master Plan:
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\HARDWARE_INTEGRATION_PLAN.md

FORENSIC AUDITOR FULL EVIDENCE REPORT (MANDATORY INGESTION):
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_auditor_1\audit.md
c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_auditor_1\handoff.md

Reviewer & Challenger Evaluation Handoffs:
- c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_reviewer_1\handoff.md
- c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_reviewer_2\handoff.md
- c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_challenger_1\handoff.md
- c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_challenger_2\handoff.md

Negative Constraints:
- Zero occurrences of Comic Sans font.
- Zero occurrences of fake 2026 Avon Corps copyright notice.

Mission:
Develop a concrete, step-by-step remediation plan addressing ALL gate failures:
1. Forensic Audit Failure Remediation:
   - Auditor found `© 2026 Avon Corps. All rights reserved.` in `experimental-hardware-merge:avon-ai/frontend/src/App.tsx` (lines 181-182) and `avon-ai/frontend/dist/assets/index-BiTr7Jg3.js` (line 67).
   - Formulate exact instructions to purge this prohibited string from `App.tsx` and delete/rebuild the `dist/` bundle so zero occurrences exist anywhere.
2. Modulino Button C Semantic Conflict:
   - Reconcile Section 3.2 Phase 4 and Section 5.2 Scene 4 so that Button C trips P-204, while proposal approvals are executed via UI button or host deck key 'a'; automated standby auto-failover to P-204 is demonstrated by pressing Button B (trips duty pump P-203).
3. 12x8 LED Matrix Bitmasks:
   - Provide the exact, mathematically verified packed 32-bit words for Section 2.3.2:
     - Frame 1 (Solid X): `packed[0] = 0x20410809`, `packed[1] = 0x00600600`, `packed[2] = 0x90108204` (Row hexes: `0x204`, `0x108`, `0x090`, `0x060`, `0x060`, `0x090`, `0x108`, `0x204`).
     - Frame 2 (Caution Triangle): `packed[0] = 0x0200500A`, `packed[1] = 0x81242024`, `packed[2] = 0x21FFF000`.
4. Hydraulic Identifiability ($w$ vs $r$):
   - Document that scalar flow $Q$ alone yields non-unique solutions ($Q=122.47$ bbl/hr for both); true differential diagnosis mathematically requires observing discharge head/pressure $P$ ($P=33.33$ psi for wear vs $P=83.33$ psi for restriction), matching `diagnosis.py:invert()`.
5. Serial Gateway Threading, Debouncing & Speed Guardrail:
   - Document background worker thread requirement for `_try_connect()` in `bridge.py` to prevent 2.5s blocking of the 10 Hz broadcast loop.
   - Document 250 ms rising-edge debouncing for Modulino Knob push-switch.
   - Document 1x speed demonstration guardrail to prevent high-speed revision drift in the approval gate.

Deliverables:
- Write comprehensive remediation plan to `c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_explorer_remediation_1\remediation_plan.md`
- Write `handoff.md` and send completion message.
