# Handoff Report: Master Hardware Integration Remediation Plan

**Agent**: `teamwork_explorer` (Remediation Explorer)  
**Date**: 2026-11-08T08:45:00Z  
**Parent Orchestrator Conversation ID**: `15fac62f-53a5-45e6-8d8c-a6a4d8181d18`  
**Type**: Hard Handoff (Investigation & Remediation Plan Complete)  
**Deliverable Path**: `c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_explorer_remediation_1\remediation_plan.md`  

---

## 1. Observation

1. **Forensic Integrity Violation (Fake Copyright Notice)**:
   - Tool Command: `Select-String -Path "avon-ai\frontend\dist\assets\index-BiTr7Jg3.js" -Pattern "Avon Corps"`
   - Result: Active match at line 67:
     `children:"c 2026 Avon Corps. All rights reserved."`
   - Tool Command: `git show experimental-hardware-merge:avon-ai/frontend/src/App.tsx | Select-String -Pattern "copyright" -Context 3,3`
   - Result: Active match at lines 181–182:
     `<span className="copyright-notice">© 2026 Avon Corps. All rights reserved.</span>`
   - Negative Constraint Check: `Comic Sans` scan returned 0 matches repository-wide.

2. **Modulino Button C Semantic Conflict**:
   - In `HARDWARE_INTEGRATION_PLAN.md` Section 2.5 (line 337):
     `Button C | P-204 | Device 3 | Emergency Trip / Reset Toggle | Toggles PUMP_TRIP fault on Standby Pump P-204`
   - In `avon-ai/hardware_gateway/bridge.py` lines 430–445:
     `trip_dev = pkt.get("trip_dev")` (Button C sends 3), which resolves to `trip_pump = "P-204"` and posts `POST /api/faults` with `PUMP_TRIP`.
   - In `HARDWARE_INTEGRATION_PLAN.md` Section 3.2 Phase 4 (line 619) & Section 5.2 Scene 4 (line 829):
     Plan states operator presses Button C to approve recommendation and wake standby pump P-204.
   - Result: Pressing Button C during Scene 4 trips pump P-204 into emergency fault lockout instead of starting it.

3. **12x8 LED Matrix Frame Packing Verification**:
   - In `HARDWARE_INTEGRATION_PLAN.md` Section 2.3.2 (lines 226–250):
     Plan documented incorrect row hexes (`0x048`...) and packed words (`0x09204809` for Frame 1; `0x020050A8` for Frame 2).
   - In `avon-ai/hardware/arduino/avon_matrix_node/src/framebuffer.cpp` lines 7–11:
     `Framebuffer::pack` implements MSB-first packing of 12-bit rows ($x=0$ at bit 11, $x=11$ at bit 0) into 3x 32-bit unsigned integers.
   - Exact mathematical derivation confirms:
     - **Frame 1 (Solid X)**: Row hexes `[0x204, 0x108, 0x090, 0x060, 0x060, 0x090, 0x108, 0x204]`; Packed words: `packed[0] = 0x20410809`, `packed[1] = 0x00600600`, `packed[2] = 0x90108204`.
     - **Frame 2 (Caution Triangle)**: Row hexes `[0x020, 0x050, 0x0A8, 0x124, 0x202, 0x421, 0xFFF, 0x000]`; Packed words: `packed[0] = 0x0200500A`, `packed[1] = 0x81242024`, `packed[2] = 0x21FFF000`.

4. **Hydraulic Identifiability ($w$ vs $r$)**:
   - Model parameters from `avon-ai/data/config.json`: $H_0 = 100, Q_{\text{max}} = 300, H_s = 20, k = 8/9000, a = 1/900$.
   - Hydraulic solver `pump_model.py:operating_point(w, s, r)`:
     - Worn pump ($w = 0.40, r = 1.00$): $Q = \sqrt{20 / (1/750)} = \mathbf{122.4745\text{ bbl/hr}}, P = 20 + (8/9000)(1.0)(15000) = \mathbf{33.33\text{ psi}}$.
     - Restricted line ($w = 1.00, r = 4.75$): $Q = \sqrt{80 / (1/187.5)} = \mathbf{122.4745\text{ bbl/hr}}, P = 20 + (8/9000)(4.75)(15000) = \mathbf{83.33\text{ psi}}$.
   - Flow rate difference: $\Delta Q = 0.0000$ bbl/hr (identical).
   - Pressure difference: $\Delta P = 50.00$ psi (separable).
   - `diagnosis.py:invert(q, p, s, cfg)` uses $(Q, P)$ to uniquely invert $(w, r)$.

5. **Serial Gateway Threading, Debounce & Speed Guardrails**:
   - In `avon-ai/hardware_gateway/bridge.py` lines 270–274: `broadcast_packet` synchronously calls `_try_connect(link)` which blocks for up to 2.5s. Microcontroller watchdog is 1.5s (`LINK_TIMEOUT_MS = 1500`), causing healthy connected boards to drop link when another board is reconnecting.
   - In `hal_peripherals.cpp` lines 48–56: `modulinoKnob.isPressed()` lacks edge detection and debounce lockout, cycling channels multiple times per finger press.
   - In `orchestrator.py` lines 361–362: `self.session.revision != ctx.revision` throws a 409 error during accelerated simulation. In `test_empirical_challenges.js`, a 12.8s Nemotron reasoning cycle at 60x speed breaches High-High ($HH = 950$ bbl) shut-in within 3.88s (+766 bbl accumulated vs 350 bbl headroom), whereas at 1x speed it accumulates only +19.2 bbl (233s to breach).

---

## 2. Logic Chain

1. *From Observation 1*: The presence of `© 2026 Avon Corps. All rights reserved.` in `App.tsx` and `dist/` directly violates the non-negotiable negative constraint. Therefore, removing the JSX element from `App.tsx` and recompiling `dist/` via `npm run build` is required before merging `experimental-hardware-merge` into `main`.
2. *From Observation 2*: Because `bridge.py` and firmware hardcode Button C to trip standby pump P-204, instructing presenters to press Button C to approve proposals will trigger a physical trip fault on stage. Therefore, Section 3.2 Phase 4 and Section 5.2 Scene 4 must be reconciled: Button C trips P-204, proposal approval is performed via UI button or deck key 'a', and standby auto-failover is demonstrated by pressing Button B to trip duty pump P-203.
3. *From Observation 3*: Because the documented packed 32-bit words in Section 2.3.2 were derived with inverted column bit ordering and row alignment errors, flashing them produces distorted noise. The exact bit calculations prove that `[0x20410809, 0x00600600, 0x90108204]` and `[0x0200500A, 0x81242024, 0x21FFF000]` are the true, bug-free packed words.
4. *From Observation 4*: Because $Q = \sqrt{\frac{w H_0 s^2 - H_s}{w a + k r}}$ is 1 equation in 2 unknowns, both $w=0.40$ and $r=4.75$ produce $Q=122.47$ bbl/hr. Observing discharge pressure $P$ provides the necessary independent degree of freedom, proving why `diagnosis.py:invert()` requires $(Q, P)$.
5. *From Observation 5*: A 2.5s blocking call in a 100 ms real-time loop exceeds a 1.5s hardware watchdog. Moving `_try_connect` to a background worker thread preserves loop timing. Adding 250 ms rising-edge debouncing stabilizes rotary channel switching. Enforcing a 1x simulation speed guardrail prevents revision conflict 409 errors and tank overflow during live AI reasoning.

---

## 3. Caveats

- **Read-Only Scope**: In strict compliance with the explorer archetype, no production source files (`App.tsx`, `bridge.py`, firmware C++ files) were directly modified during this turn. All precise patch snippets, git commands, and code blocks have been formulated and verified in `remediation_plan.md` for immediate execution by the worker/implementer.
- **Physical Silicon Bench Execution**: Microcontroller verification was performed against the exact C++ packing algorithms, bitmask coordinates, and serial protocol specifications rather than flashing physical Renesas RA4M1 silicon.

---

## 4. Conclusion

All five gate failures have been rigorously analyzed, cross-verified, and reconciled into a unified, actionable specification:
1. **Forensic Integrity**: Detailed atomic instructions to purge `<span className="copyright-notice">` from `App.tsx`, delete/rebuild `dist/`, and verify zero occurrences repository-wide.
2. **Button C Semantics**: Full control contract reconciliation ensuring Button C trips P-204, approvals occur via UI / key 'a', and auto-failover is demonstrated via Button B.
3. **LED Matrix Bitmasks**: Bit-by-bit verified packed 32-bit words matching `Framebuffer::pack` for Solid X and Caution Triangle.
4. **Hydraulic Identifiability**: Closed-form mathematical proof demonstrating $Q=122.47$ bbl/hr non-identifiability and $P$ discharge head disambiguation matching `diagnosis.py:invert()`.
5. **Gateway Threading & Guardrails**: Non-blocking background worker thread architecture for `bridge.py`, 250 ms rising-edge debouncing for `hal_peripherals.cpp`, and 1x speed demonstration guardrail.

The complete master plan is documented at:
`c:\Users\avisi\Documents\GitHub\AvonAI-SecondPass\.agents\teamwork\teamwork_explorer_remediation_1\remediation_plan.md`

---

## 5. Verification Method

To independently verify all findings and remediation specifications:

1. **Verify Prohibited String & Branch State**:
   ```powershell
   Select-String -Path "avon-ai\frontend\dist\assets\index-BiTr7Jg3.js" -Pattern "Avon Corps"
   git show experimental-hardware-merge:avon-ai/frontend/src/App.tsx | Select-String -Pattern "Avon Corps"
   ```

2. **Verify Bitmask Packing Math**:
   ```bash
   node -e "
   const unpack = (words) => {
     let g = Array.from({length: 8}, () => Array(12).fill('.'));
     words.forEach((w, idx) => {
       for (let b = 0; b < 32; b++) {
         if ((w >>> (31 - b)) & 1) {
           let i = idx * 32 + b;
           if (i < 96) g[Math.floor(i / 12)][i % 12] = '#';
         }
       }
     });
     return g.map(r => r.join('')).join('\n');
   };
   console.log('--- SOLID X ---\n' + unpack([0x20410809, 0x00600600, 0x90108204]));
   console.log('--- CAUTION TRIANGLE ---\n' + unpack([0x0200500A, 0x81242024, 0x21FFF000]));
   "
   ```

3. **Verify Hydraulic $Q$ Equivalence & $P$ Disambiguation**:
   ```bash
   node -e "
   const H0=100, Hs=20, a=1/900, k=8/9000;
   const solve = (w, r) => {
     const Q = Math.sqrt((w*H0 - Hs)/(w*a + k*r));
     const P = Hs + k*r*Q*Q;
     return { Q: Q.toFixed(4), P: P.toFixed(4) };
   };
   console.log('Wear (w=0.40, r=1.00):', solve(0.40, 1.00));
   console.log('Restriction (w=1.00, r=4.75):', solve(1.00, 4.75));
   "
   ```
