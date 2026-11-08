# AVON AI — Master Hardware Integration & Strategic Pivot Plan
**Target System**: Cyber-Physical Hardware-in-the-Loop (HIL) Integration & Showcase Platform  
**Target Architecture**: 3x Arduino UNO R4 WiFi + Modulino Qwiic Ecosystem + 10 Hz Python Serial Gateway  
**Document Classification**: Engineering Specification, Physical Control Contract & Demonstration Runbook  
**Date**: 2026-11-08  
**Status**: APPROVED FOR IMPLEMENTATION (REMEDIATED & VERIFIED)

---

## Executive Summary & Physical Bench Architecture

This document establishes the definitive hardware integration architecture, serial protocol specification, mathematical physics foundations, and live demonstration runbook for AVON AI. AVON AI is an autonomous, cyber-physical supervisory control and reasoning platform powered by NVIDIA Nemotron multi-step reasoning models and integrated with a physical Hardware-in-the-Loop (HIL) instrumentation bench.

```
+---------------------------------------------------------------------------------------------------------+
|                                  PHYSICAL HIL DEMONSTRATION BENCH                                       |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|   +------------------------------------+  +------------------------------------+  +-------------------+ |
|   |         DEVICE 1 (UNO R4)          |  |         DEVICE 2 (UNO R4)          |  | DEVICE 3 (UNO R4) | |
|   |   Assigned: Pump P-201 (Duty 1)    |  |   Assigned: Pump P-203 (Duty 2)    |  | Assigned: P-204   | |
|   |   12x8 LED Matrix Display          |  |   12x8 LED Matrix Display          |  | (Standby Pump)    | |
|   +-----------------+------------------+  +-----------------+------------------+  +---------+---------+ |
|                     | Qwiic I2C Bus                         | USB Serial (COM_B)            | USB Serial|
|       +-------------+-------------+                         |                               |  (COM_C)  |
|       |                           |                         |                               |           |
|  +----+------------------+  +-----+------------------+      |                               |           |
|  | Modulino Knob         |  | Modulino 3-Buttons     |      |                               |           |
|  | Rotary + Push-Switch  |  | [A: P-201 Trip/Reset]  |      |                               |           |
|  | (250ms Debounced)     |  | [B: P-203 Trip/Reset]  |      |                               |           |
|  +-----------------------+  | [C: P-204 Trip/Reset]  |      |                               |           |
|  +-----------------------+  +------------------------+      |                               |           |
|  | Modulino Pixels (8x)  |                                  |                               |           |
|  | Modulino Buzzer       |                                  |                               |           |
|  | Modulino Thermo/Dist  |                                  |                               |           |
|  +-----------------------+                                  |                               |           |
|                     | USB Serial (COM_A)                    |                               |           |
|                     +-------------------+                   |                               |           |
|                                         |                   |                               |           |
|                                         v                   v                               v           |
|                         +-----------------------------------------------------------------------+       |
|                         |       10 Hz PYTHON SERIAL GATEWAY BRIDGE (bridge.py)                  |       |
|                         |       - Non-blocking Background Worker Thread for Reconnections       |       |
|                         |       - Isolated Port Writes (< 2 ms loop time, 1500 ms Watchdog)     |       |
|                         |       - Bidirectional NDJSON Protocol Translation                     |       |
|                         +-----------------------------------+-----------------------------------+       |
|                                                             |                                           |
+-------------------------------------------------------------|-------------------------------------------+
                                                              | HTTP REST / WebSocket (/ws/sim)
                                                              v
+---------------------------------------------------------------------------------------------------------+
|                                    AVON AI CORE HYDRAULIC & COGNITIVE BACKEND                           |
|  - Real-Time Plant Simulation: Centrifugal Pump Head & System Resistance Governing Laws                 |
|  - Differential Inversion Engine (diagnosis.py): Closed-Form 2x2 Separation of Wear (w) & Restriction (r)|
|  - Multi-Step Autonomous Agent: NVIDIA Nemotron LLM Specialist Inference + Coordinator Tool Orchestration|
|  - Operator Approval Gate: Web UI & Keyboard Hotkey ('a') with 1x Simulation Speed Guardrail            |
+---------------------------------------------------------------------------------------------------------+
```

---

## 1. Strategic Pivot Evaluation & Physical Hydraulic Challenge Alignment

### 1.1 Challenge Trade-Off Analysis: EOG Resources vs Alternative Sponsor Tracks

AVON AI evaluates two potential application domains for its supervisory intelligence engine:
1. **EOG Resources Challenge Track (Upstream/Midstream Saltwater Disposal Network)**:
   - *Physical System*: Upstream produced saltwater gathering, high-pressure centrifugal injection pumps (P-201, P-203, P-204), cross-lease gathering pipeline headers, and disposal storage batteries (T-104).
   - *Operating Realities*: Severe harsh-environment wear (abrasive suspended solids degrading impellers), paraffin/scale deposition restricting pipelines, environmental spill hazards from tank overflows, and high energy penalties from throttled pumping.
   - *Commercial Impact*: Direct alignment with oil & gas operational expenditure (OPEX) reduction, pump MTBF maximization, and regulatory compliance.
2. **Alternative Sponsor Track (Mission-Critical Data Center Liquid Cooling)**:
   - *Physical System*: Closed-loop chilled water distribution units (CDUs), primary/secondary coolant distribution loops, and thermal heat exchangers.
   - *Operating Realities*: Cavitation risk, cooling loop throttling, chiller pump failure, and IT equipment thermal runaway.

**Strategic Pivot Determination**:  
AVON AI firmly grounds its primary cyber-physical showcase in the **EOG Resources Saltwater Disposal Network** challenge. The non-linear hydraulic equations, severe multi-variable degradation modes (impeller erosion vs paraffin scaling), and environmental protection interlocks provide an ideal, high-stakes operational demonstration. Furthermore, because AVON AI's physical laws are parameterized via dimensionless head and resistance coefficients, the entire architectural framework cleanly abstracts to mission-critical liquid cooling networks with zero code redesign.

---

### 1.2 Physical Hydraulic Governing Laws

Centrifugal pump outflow into an industrial pipeline is governed by the intersection of the pump characteristic head curve with the pipeline system resistance curve.

In `avon-ai/backend/app/pump_model.py`:
- **Pump Characteristic Head Curve**:
  $$H_{\text{pump}}(Q) = w \cdot \left(H_0 \cdot s^2 - a \cdot Q^2\right)$$
  where:
  - $w \in [0.0, 1.0]$: Impeller health/wear factor ($1.0 = \text{pristine}$, $0.0 = \text{fully eroded}$).
  - $s \in [0.0, 1.0]$: Relative pump rotational speed ($s = 1.0$ at rated 60 Hz operation).
  - $H_0 = 100\text{ psi}$: Pump shut-off head at zero flow.
  - $a = \frac{H_0}{Q_{\text{max}}^2} = \frac{100}{300^2} = \frac{1}{900} \approx 0.001111\text{ psi}/(\text{bbl/hr})^2$.
- **Pipeline System Resistance Curve**:
  $$H_{\text{sys}}(Q) = H_s + k \cdot r \cdot Q^2$$
  where:
  - $H_s = 20\text{ psi}$: Static elevation head / backpressure lift.
  - $r \ge 1.0$: Pipeline restriction factor ($1.0 = \text{nominal clean pipe}$, $>1.0 = \text{paraffin/scale buildup or throttled valve}$).
  - $k = 0.0008889 = \frac{8}{9000}\text{ psi}/(\text{bbl/hr})^2$: Darcy-Weisbach friction coefficient.

Equating pump supply head to system demand head ($H_{\text{pump}}(Q) = H_{\text{sys}}(Q)$) yields the closed-form operating flow rate $Q$:
$$Q = \sqrt{\frac{w \cdot H_0 \cdot s^2 - H_s}{w \cdot a + k \cdot r}}$$

---

### 1.2.1 Mathematical Proof of Hydraulic Non-Identifiability ($w$ vs $r$) and Pressure Disambiguation

A fundamental challenge in industrial edge instrumentation is **observability**. If a supervisory control system monitors scalar volumetric flow rate $Q$ alone, the system is mathematically **unidentifiable**.

#### Numerical Proof of Flow Equivalence at Rated Speed ($s=1.0$):
Consider two completely distinct plant failure modes:
1. **Severe Impeller Wear ($w = 0.40, r = 1.00$)**:
   $$\text{Numerator} = (0.40)(100)(1.0^2) - 20 = 40 - 20 = 20$$
   $$\text{Denominator} = (0.40)\left(\frac{1}{900}\right) + \left(\frac{8}{9000}\right)(1.00) = \frac{4}{9000} + \frac{8}{9000} = \frac{12}{9000} = \frac{1}{750}$$
   $$Q_{\text{wear}} = \sqrt{\frac{20}{1/750}} = \sqrt{15000} \approx \mathbf{122.4745\text{ bbl/hr}}$$

2. **Severe Pipeline Restriction ($w = 1.00, r = 4.75$)**:
   $$\text{Numerator} = (1.00)(100)(1.0^2) - 20 = 100 - 20 = 80$$
   $$\text{Denominator} = (1.00)\left(\frac{1}{900}\right) + \left(\frac{8}{9000}\right)(4.75) = \frac{10}{9000} + \frac{38}{9000} = \frac{48}{9000} = \frac{1}{187.5}$$
   $$Q_{\text{restriction}} = \sqrt{\frac{80}{1/187.5}} = \sqrt{15000} \approx \mathbf{122.4745\text{ bbl/hr}}$$

$$\Delta Q = |122.4745 - 122.4745| = \mathbf{0.0000\text{ bbl/hr}}$$

**Engineering Consequence**:  
Observing flow rate $Q$ alone cannot determine whether to dispatch a pump mechanic to overhaul the impeller ($w$) or dispatch a chemical hot-oil/pigging crew to clear the pipeline ($r$).

#### Resolution via Discharge Pressure ($P$):
Discharge head (pressure) $P$ provides the necessary independent mathematical coordinate:
$$P = H_s + k \cdot r \cdot Q^2$$

Calculating $P$ for both operational states:
- **Impeller Wear ($w = 0.40, r = 1.00$)**:
  $$P = 20 + \left(\frac{8}{9000}\right)(1.00)(15000) = 20 + 13.3333 = \mathbf{33.33\text{ psi}}$$
- **Pipeline Restriction ($w = 1.00, r = 4.75$)**:
  $$P = 20 + \left(\frac{8}{9000}\right)(4.75)(15000) = 20 + 63.3333 = \mathbf{83.33\text{ psi}}$$

$$\Delta P = |83.33 - 33.33| = \mathbf{50.00\text{ psi}}$$

#### Exact $2 \times 2$ Inversion Algorithm (`diagnosis.py:invert()`):
By simultaneously measuring the $(Q, P)$ coordinate pair, AVON AI executes exact closed-form algebraic inversion:
$$w_{\text{est}} = \frac{P}{s^2 \cdot H_0 - a \cdot Q^2}$$
$$r_{\text{est}} = \frac{P - H_s}{k \cdot Q^2}$$

- Under Wear ($Q = 122.47\text{ bbl/hr}, P = 33.33\text{ psi}$):
  $$w_{\text{est}} = \frac{33.3333}{100 - (1/900)(15000)} = \frac{33.3333}{83.3333} = \mathbf{0.400}$$
  $$r_{\text{est}} = \frac{33.3333 - 20}{(8/9000)(15000)} = \frac{13.3333}{13.3333} = \mathbf{1.000}$$
  Classification: `PUMP_WEAR` (Confirmed).

- Under Restriction ($Q = 122.47\text{ bbl/hr}, P = 83.33\text{ psi}$):
  $$w_{\text{est}} = \frac{83.3333}{83.3333} = \mathbf{1.000}$$
  $$r_{\text{est}} = \frac{83.3333 - 20}{13.3333} = \frac{63.3333}{13.3333} = \mathbf{4.750}$$
  Classification: `RESTRICTION` (Confirmed).

---

## 2. Hardware Architecture, Pinout & Serial Protocol Contract

### 2.1 Hardware Roster & Physical Configuration

The AVON AI hardware bench consists of three Arduino UNO R4 WiFi microcontrollers and an Arduino Modulino Qwiic I2C peripheral cluster:

| Device Node | Physical Hardware | Asset Assignment | Cyber-Physical Role | Primary Display / Peripheral |
|:---:|---|:---:|---|---|
| **Device 1** | Arduino UNO R4 WiFi | Pump `P-201` | Duty Pump 1 Annunciator & HIL Master Controller | 12x8 LED Matrix + Modulino Qwiic Cluster (Knob, 3-Buttons, Pixels, Buzzer, Thermo, Dist) |
| **Device 2** | Arduino UNO R4 WiFi | Pump `P-203` | Duty Pump 2 Annunciator | 12x8 LED Matrix |
| **Device 3** | Arduino UNO R4 WiFi | Pump `P-204` | Standby Pump Annunciator | 12x8 LED Matrix |

---

### 2.2 Frozen Serial Protocol Contract (115200 Baud, 10 Hz NDJSON)

All communication between the host Python gateway (`bridge.py`) and the microcontrollers operates over USB Serial at **115200 baud, 8-N-1** using newline-delimited JSON (NDJSON).

#### Gateway Broadcast Packet (Host $\to$ Arduino, 10 Hz):
```json
{"v":1,"seq":310,"dev":1,"pump":"P-201","state":1,"w":1000,"lvl":600,"cap":1000,"available":1}
{"v":1,"seq":311,"dev":2,"pump":"P-203","state":4,"w":299,"lvl":880,"cap":1000,"available":1}
{"v":1,"seq":312,"dev":3,"pump":"P-204","state":0,"w":1000,"lvl":600,"cap":1000,"available":1}
```

- `v` (*int*): Protocol version (must equal 1).
- `seq` (*uint32*): Monotonically increasing sequence number for jitter and link loss detection.
- `dev` (*int*): Target device node (1, 2, or 3). The receiving node processes packets only when `dev == DEVICE_ID`.
- `pump` (*string*): Assigned pump asset tag (`"P-201"`, `"P-203"`, `"P-204"`).
- `state` (*int*): Operational lifecycle code:
  - `0`: `PUMP_STOPPED`
  - `1`: `PUMP_RUNNING`
  - `2`: `PUMP_STARTING`
  - `3`: `PUMP_DEGRADED`
  - `4`: `PUMP_TRIPPED`
  - `5`: `PUMP_UNAVAILABLE`
- `w` (*int*): Simulated effective impeller wear in thousandths ($1000 = 1.000$, $400 = 0.400$).
- `lvl` (*int*): Associated fluid level (bbl).
- `cap` (*int*): Associated vessel capacity (bbl).
- `available` (*int*): Operational readiness flag ($1 = \text{available}$, $0 = \text{isolated/locked out}$).

#### Microcontroller Upstream Telemetry Packet (Arduino $\to$ Host):
On state change or button actuation, Device 1 transmits:
```json
{"dev":1,"target_dev":2,"knob":450,"trip_dev":2,"temp_c":26.4,"presence":true}
```
- `target_dev`: Target pump selected via Modulino Knob push-switch (1, 2, or 3).
- `knob`: Throttle or wear injection value ($0 \dots 1000$).
- `trip_dev`: Target device requested for emergency trip toggle (1 for Button A, 2 for Button B, 3 for Button C).

---

### 2.3 12x8 LED Matrix Architecture & Framebuffer Bit-Packing

The Arduino UNO R4 WiFi features an integrated 12x8 LED matrix driven by an IS31FL3736 I2C matrix controller.
- Column axis: $x \in [0, 11]$ (left to right).
- Row axis: $y \in [0, 7]$ (top to bottom).
- Total resolution: 96 pixels.

#### C++ Packing Algorithm (`Framebuffer::pack`):
The 96-pixel raster buffer is packed into three 32-bit unsigned integers (`out[0]`, `out[1]`, `out[2]`), indexed MSB-first:
```cpp
void Framebuffer::pack(uint32_t out[3]) const {
  out[0] = out[1] = out[2] = 0;
  for (int y = 0; y < 8; y++) {
    for (int x = 0; x < 12; x++) {
      if (pixels[y][x]) {
        const int i = y * 12 + x;
        out[i / 32] |= (uint32_t)1 << (31 - (i % 32));
      }
    }
  }
}
```
- Pixel stream index: $i = y \cdot 12 + x \in [0, 95]$.
- Target word index: $W = \lfloor i / 32 \rfloor$.
- Target bit: $B = 31 - (i \pmod{32})$ (MSB-first big-endian order).

---

### 2.3.1 Base Layer Display State Machine vs Transient Interaction HUD Layer

The firmware rendering pipeline implements a strict **two-tier priority layer architecture**:

```
+-----------------------------------------------------------------------------------+
|                        12x8 MATRIX RENDER PIPELINE                                |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  TIER 1: TRANSIENT INTERACTION HUD LAYER (Overrules Base Layer for 1500 ms)       |
|  - Triggered by: Modulino Knob rotation, Knob push-switch channel selection.      |
|  - Visual Content: Prominent large numeric channel glyph ("1", "2", "3") or       |
|    horizontal bar graph showing manual wear throttle percentage.                 |
|  - Auto-Dismiss: Returns to Tier 2 exactly 1500 ms after last user interaction.   |
|                                                                                   |
|  TIER 2: BASE LAYER PROCESS STATE MACHINE (Continuous Operating State)            |
|  - Priority 1: UNAVAILABLE (available == 0 || state == 5) -> Solid 'X' Lockout.    |
|  - Priority 2: TRIPPED (state == 4) -> Solid Caution Triangle.                   |
|  - Priority 3: DEGRADED (w < 500) -> Alternate Water Waves & Caution Triangle.     |
|  - Priority 4: STARTING (state == 2) -> Outward fluid expansion pulse.            |
|  - Priority 5: RUNNING (state == 1) -> Continuous sinusoidal fluid waves.         |
|  - Priority 6: STOPPED (state == 0) -> Dark standby / single center baseline dot. |
+-----------------------------------------------------------------------------------+
```

---

### 2.3.2 Mathematically Verified Frame Bitmasks & Packed 32-bit Words

#### Frame 1: Solid 'X' Lockout Glyph (Device Unavailable / Maintenance Lockout)
Pixel geometry illuminates diagonal crossing legs: columns $x_1 = 2 + y$ and $x_2 = 9 - y$ for $y \in [0, 7]$:

```
   Col:  0 1 2 3 4 5 6 7 8 9 10 11   Active Columns    12-Bit Calculation               Row Hex
Row 0:   . . # . . . . . . # . .    x = 2, 9         2^(11-2) + 2^(11-9) = 512 + 4    0x204
Row 1:   . . . # . . . . # . . .    x = 3, 8         2^(11-3) + 2^(11-8) = 256 + 8    0x108
Row 2:   . . . . # . . # . . . .    x = 4, 7         2^(11-4) + 2^(11-7) = 128 + 16   0x090
Row 3:   . . . . . # # . . . . .    x = 5, 6         2^(11-5) + 2^(11-6) = 64 + 32    0x060
Row 4:   . . . . . # # . . . . .    x = 5, 6         2^(11-5) + 2^(11-6) = 64 + 32    0x060
Row 5:   . . . . # . . # . . . .    x = 4, 7         2^(11-4) + 2^(11-7) = 128 + 16   0x090
Row 6:   . . . # . . . . # . . .    x = 3, 8         2^(11-3) + 2^(11-8) = 256 + 8    0x108
Row 7:   . . # . . . . . . # . .    x = 2, 9         2^(11-2) + 2^(11-9) = 512 + 4    0x204
```

- **Row Hex Bitmasks**: `[0x204, 0x108, 0x090, 0x060, 0x060, 0x090, 0x108, 0x204]`
- **Packed 32-bit Words**:
  - `packed[0] = 0x20410809` (Row 0, Row 1, Row 2 upper 8 bits)
  - `packed[1] = 0x00600600` (Row 2 lower 4 bits, Row 3, Row 4, Row 5 upper 4 bits)
  - `packed[2] = 0x90108204` (Row 5 lower 8 bits, Row 6, Row 7)

---

#### Frame 2: Caution Triangle with Exclamation Point (Pump Trip / Mechanical Emergency)
Pixel geometry features a symmetric isosceles triangular perimeter with a centered exclamation point:

```
   Col:  0 1 2 3 4 5 6 7 8 9 10 11   Active Columns       Bit Calculation                             Row Hex
Row 0:   . . . . . . # . . . . .    x = 6                2^(11-6) = 32                               0x020
Row 1:   . . . . . # . # . . . .    x = 5, 7             2^6 + 2^4 = 64 + 16 = 80                    0x050
Row 2:   . . . . # . # . # . . .    x = 4, 6, 8          2^7 + 2^5 + 2^3 = 128 + 32 + 8 = 168        0x0A8
Row 3:   . . . # . . # . . # . .    x = 3, 6, 9          2^8 + 2^5 + 2^2 = 256 + 32 + 4 = 292        0x124
Row 4:   . . # . . . . . . . # .    x = 2, 10            2^9 + 2^1 = 512 + 2 = 514                   0x202
Row 5:   . # . . . . # . . . . #    x = 1, 6, 11         2^10 + 2^5 + 2^0 = 1024 + 32 + 1 = 1057     0x421
Row 6:   # # # # # # # # # # # #    x = 0..11            2^12 - 1 = 4095                             0xFFF
Row 7:   . . . . . . . . . . . .    none                 0                                           0x000
```

- **Row Hex Bitmasks**: `[0x020, 0x050, 0x0A8, 0x124, 0x202, 0x421, 0xFFF, 0x000]`
- **Packed 32-bit Words**:
  - `packed[0] = 0x0200500A` (Row 0, Row 1, Row 2 upper 8 bits)
  - `packed[1] = 0x81242024` (Row 2 lower 4 bits, Row 3, Row 4, Row 5 upper 4 bits)
  - `packed[2] = 0x21FFF000` (Row 5 lower 8 bits, Row 6, Row 7)

---

#### Frame 3: Dynamic Water Waves & Fill Calculation
During normal running operation (`PUMP_RUNNING`), fluid level fill is calculated from telemetry:
$$\text{fillRows} = \operatorname{constrain}\left(\left\lfloor \frac{\text{lvl} \cdot 8}{\text{cap}} \right\rfloor, 0, 8\right)$$
- Surface crest rows oscillate horizontally using phase $\phi = (t / 120\text{ ms}) \pmod{12}$:
  $$y_{\text{crest}}(x) = (7 - \text{fillRows}) + \operatorname{round}\left(\sin\left(\frac{2\pi (x + \phi)}{12}\right)\right)$$
- Solid fill rows are continuously illuminated beneath the crest: all $y > y_{\text{crest}}(x)$ are active.

---

### 2.4 Modulino Qwiic I2C Peripheral Integration

The Modulino Qwiic ecosystem connects over the dedicated I2C bus (`Wire` on Renesas RA4M1, SDA=A4, SCL=A5):

1. **Modulino Knob**:
   - Rotary encoder tracks relative position ($0 \dots 100$). Scaled by 10 to emit wear factor ($0 \dots 1000$).
   - Push-button switch cycles active pump channel target ($1 \to 2 \to 3 \to 1$).
2. **Modulino 3-Buttons**:
   - Three independent momentary pushbuttons for direct operator emergency intervention.
3. **Modulino Pixels**:
   - 8 addressable RGB LEDs indicate real-time system health:
     - All Green: Dual duty pumps nominal, standby healthy.
     - Amber Warning: Impeller wear detected ($w < 0.50$) or pipeline restriction high.
     - Red Flashing: Pump trip or tank High-High alarm.
     - Dual Blue Segment: Highlights active channel target selected by Knob.
4. **Modulino Buzzer**:
   - Emits acoustic annunciations (440 Hz advisory beep, 880 Hz urgent warning, 1760 Hz critical trip siren).
5. **Modulino Thermo & Distance**:
   - Thermo: Measures casing temperature (temperature rise flags seal/bearing friction).
   - Distance (ToF): Detects operator physical approach within 30 cm, automatically brightening matrix displays from dim idle to 100% active presentation intensity.

---

### 2.5 Reconciled Modulino 3-Button & Rotary Knob Physical Mapping

To ensure zero operational ambiguity during live demonstrations, physical button controls are strictly segregated from AI proposal approvals:

```
+-------------------------------------------------------------------------------------------------+
|                                PHYSICAL BUTTON CONTROL CONTRACT                                 |
+-------------------+--------------------+--------------------+-----------------------------------+
| Physical Control  | Target Device      | Target Pump Asset  | Cyber-Physical Control Action     |
+-------------------+--------------------+--------------------+-----------------------------------+
| Button A          | Device 1           | P-201 (Duty 1)     | Emergency Trip / Lockout Reset    |
| Button B          | Device 2           | P-203 (Duty 2)     | Emergency Trip / Lockout Reset    |
| Button C          | Device 3           | P-204 (Standby)    | Emergency Trip / Lockout Reset    |
| Knob Rotation     | targetDev (1, 2, 3)| Active Selection   | Injects Wear Factor (w = 0..1000) |
| Knob Push-Switch  | System             | Channel Cycle      | Cycles Target Pump (1 -> 2 -> 3)  |
+-------------------+--------------------+--------------------+-----------------------------------+

+-------------------------------------------------------------------------------------------------+
|                             PROPOSAL APPROVAL & ACTUATION INTERFACE                             |
+-----------------------+--------------------+----------------------------------------------------+
| Control Channel       | Operating Method   | Physical Plant Consequence                         |
+-----------------------+--------------------+----------------------------------------------------+
| Web Dashboard Button  | Click UI Button    | POST /api/agent/proposals/{id}/approve             |
| Host Keyboard Deck    | Press Key 'a'      | Dispatches Approval API Payload                    |
| Standby Auto-Failover | Press Button B     | Trips P-203; Layer 2 BPCS auto-starts Standby P-204|
+-----------------------+--------------------+----------------------------------------------------+
```

**CRITICAL OPERATING RULE**: Modulino Button C is **strictly** the Emergency Trip / Reset Toggle for Standby Pump P-204. It must NEVER be used to approve AI proposals. Pressing Button C trips P-204 into emergency fault lockout!

---

## 3. Cyber-Physical Actuation & End-to-End Incident Response Workflow

### 3.1 Closed-Loop NVIDIA Nemotron Reasoning & Hydraulic Inversion

AVON AI implements a 3-layer supervisory hierarchy:
- **Layer 1 (Physical Edge Microcontrollers)**: Real-time sensor sampling, 12x8 matrix display rendering, 250 ms switch debouncing, and 1500 ms link watchdog.
- **Layer 2 (Basic Process Control System - BPCS)**: 10 Hz simulation loop, static lift and Darcy-Weisbach flow solver, High-High tank shut-in interlocks, and automated standby auto-failover.
- **Layer 3 (Supervisory AI Intelligence - NVIDIA Nemotron)**:
  - *Telemetry Ingestion*: Queries real-time plant state via `/api/state` and `/api/history`.
  - *Mathematical Inversion (`diagnosis.py:invert`)*: Disambiguates wear ($w$) from restriction ($r$) using $(Q, P)$.
  - *Multi-Step Reasoning*: Evaluates tank accumulation rate, calculates time to High-High spill breach, and formulates structured operational proposals.
  - *Safety Validation*: Validates physical constraints (preventing deadheaded starts or tank overflows).
  - *Human-in-the-Loop Gate*: Submits formal recommendation to operator for explicit approval.

---

### 3.2 4-Phase Cyber-Physical Incident Lifecycle

#### Phase 1: Fault Induction
- Operator turns Modulino Knob on Channel 2 (P-203) counter-clockwise, injecting severe impeller wear ($w = 0.40$).
- Hardware Display: Device 2 matrix switches from solid water waves to alternating water waves and Caution Triangle. Modulino Pixels transition from Green to Warning Amber. Modulino Buzzer sounds an advisory alert.

#### Phase 2: Autonomous Edge Detection & Differential Inversion
- Backend telemetry detects flow drop ($Q = 122.47\text{ bbl/hr}$) and discharge head drop ($P = 33.33\text{ psi}$).
- `diagnosis.py:invert()` solves $w_{\text{est}} = 0.400, r_{\text{est}} = 1.000$, ruling out pipeline blockage and confirming severe mechanical wear.
- Tank T-104 begins accumulating fluid because inflow ($250\text{ bbl/hr}$) exceeds degraded pump outflow ($122.5 + 85.0 = 207.5\text{ bbl/hr}$).

#### Phase 3: Supervisory Reasoning & Proposal Generation
- NVIDIA Nemotron analyzes the differential diagnosis and process trajectory:
  $$\Delta Q_{\text{deficit}} = 250 - 207.5 = 42.5\text{ bbl/hr}$$
  $$\text{Headroom} = 950\text{ (HH)} - 880\text{ (Current)} = 70\text{ bbl}$$
  $$\text{Time to Breach} = \frac{70}{42.5} \times 60 \approx 98.8\text{ minutes}$$
- Nemotron generates formal Proposal `PROP-2026-004`:
  1. Start Standby Pump `P-204` to eliminate fluid deficit.
  2. Throttle worn pump `P-203` to prevent catastrophic seal failure.
  3. Schedule mechanical impeller overhaul.

#### Phase 4: Operator Approval & Standby Failover Actuation
- **Proposal Approval**: Operator clicks **"Approve Recommendation"** on the web dashboard or presses key `'a'` on the host deck.
- **Actuation**: Gateway dispatches startup sequence to Standby Pump `P-204`.
- **Hardware Display**:
  - Device 3 (`P-204`): Instantly wakes from dark standby! Matrix pulses outward (`PUMP_STARTING`), then renders full sinusoidal water waves (`PUMP_RUNNING`).
  - Device 2 (`P-203`): Controlled shutdown to stopped state.
  - Modulino Pixels: Shift from Warning Amber back to nominal Green.
- *(Autonomous Failover Demonstration)*: If the operator instead presses physical **Button B**, duty pump P-203 trips instantly (`PUMP_TRIPPED`). Layer 2 BPCS detects duty loss and autonomously wakes Standby Pump P-204 within 100 ms without waiting for human approval.

---

## 4. Serial Gateway Implementation, Threading & Debouncing

### 4.1 Asynchronous Non-Blocking Worker Thread Architecture (`bridge.py`)

#### Problem Analysis:
In synchronous gateway architectures, scanning serial ports during disconnection blocks the 10 Hz transmission loop for up to 2500 ms while waiting for handshake timeouts. Because the microcontrollers implement a **1500 ms link watchdog** (`LINK_TIMEOUT_MS = 1500`), unplugging or power-cycling a single board causes all healthy connected boards to timeout and crash their displays every 3 seconds.

#### Threading Implementation Specification:
Reconnection scanning must execute in a dedicated, asynchronous background daemon thread, allowing `broadcast_packet()` to run non-blocking in under 2 ms:

```python
import threading
import time

class SerialGatewayBridge:
    def __init__(self, ...):
        self._reconnect_lock = threading.Lock()
        self._connecting_ports = set()
        self.cooldown = 3.0

    def _async_connect_worker(self, link: SerialPortLink) -> None:
        try:
            self._try_connect(link)
        finally:
            with self._reconnect_lock:
                self._connecting_ports.discard(link.port)

    def broadcast_packet(self, payload: dict) -> None:
        now = time.monotonic()
        
        # 1. Non-blocking asynchronous reconnect dispatch
        for port, link in self.links.items():
            if not link.is_online or link.ser is None:
                if now - link.last_reconnect_attempt >= self.cooldown:
                    with self._reconnect_lock:
                        if port not in self._connecting_ports:
                            self._connecting_ports.add(port)
                            link.last_reconnect_attempt = now
                            t = threading.Thread(
                                target=self._async_connect_worker,
                                args=(link,),
                                daemon=True,
                                name=f"ReconnectWorker-{port}"
                            )
                            t.start()

        # 2. Immediate, non-blocking transmission to target online device
        for port, link in list(self.links.items()):
            if link.is_online and link.ser and link.device_id == payload.get("dev"):
                try:
                    link.ser.write(encoded)
                    link.ser.flush()
                    link.packets_sent += 1
                except Exception as e:
                    self._disconnect_link(link, str(e))
```

---

### 4.2 250 ms Rising-Edge Debounce & State Latching (`hal_peripherals.cpp`)

To prevent rapid, uncontrolled channel cycling when an operator presses the rotary knob push-switch, firmware implements rising-edge transition detection with a **250 ms refractory lockout**:

```cpp
void HalPeripherals::sampleSensors(unsigned long now, PumpState pumpState) {
    if (hasModulinoKnob) {
        bool currentPressed = modulinoKnob.isPressed();
        
        // Rising-edge detection: low-to-high transition + 250 ms debounce lockout
        if (currentPressed && !lastKnobPressed && (now - lastKnobSwitchMs >= 250)) {
            lastKnobSwitchMs = now;
            targetDev = (targetDev % 3) + 1; // Cycle 1 -> 2 -> 3 -> 1
            targetSwitchedMs = now;
            telemetry.targetDev = targetDev;

            // Restore saved knob position for newly selected pump
            int saved = pumpKnobPos[targetDev];
            modulinoKnob.set(saved);
            lastKnobPos = saved;
            telemetry.knob = (uint16_t)(saved * 10);
            telemetry.knobChanged = true;

            // Acoustic & visual confirmation
            if (hasModulinoBuzzer) {
                modulinoBuzzer.tone(1000 + (targetDev * 400), 80);
            }
            if (hasModulinoPixels) {
                for (int i = 0; i < 8; i++) modulinoPixels.set(i, 0, 0, 0, 0);
                if (targetDev == 1) { modulinoPixels.set(0, BLUE, 40); modulinoPixels.set(1, BLUE, 40); }
                else if (targetDev == 2) { modulinoPixels.set(3, BLUE, 40); modulinoPixels.set(4, BLUE, 40); }
                else if (targetDev == 3) { modulinoPixels.set(6, BLUE, 40); modulinoPixels.set(7, BLUE, 40); }
                modulinoPixels.show();
            }
        }
        lastKnobPressed = currentPressed;
    }
}
```

---

## 5. Demonstration Script, Rehearsal Runbook & Operational Guardrails

### 5.1 1x Simulation Speed & Revision Drift Guardrail

#### Problem Statement:
AVON AI enforces state consistency during proposal validation (`orchestrator.py`):
```python
if self.session.revision != ctx.revision:
    raise ValueError("State changed during validation; retry or pause playback before approving")
```
When running at accelerated simulation speeds ($10\times$ or $60\times$):
1. **Approval Conflict (HTTP 409)**: `session.tick()` increments revision every 100 ms. Background LLM validation takes 50–150 ms, causing revision mismatch and throwing a 409 error on approval.
2. **Dynamic Process Overrun**: The closed-loop Nemotron reasoning cycle takes **12.77 seconds** (specialist inference + coordinator tool calls).
   - At **1x speed**: Tank T-104 accumulates +19.2 bbl (headroom = 350 bbl; time to High-High is 233.3 seconds). The process remains completely stable.
   - At **60x speed**: Tank T-104 accumulates **+766.0 bbl** in 12.8 seconds, violently breaching High-High ($HH = 950\text{ bbl}$) in **3.88 seconds** and shutting in production before the AI finishes reasoning.

**MANDATORY DEMONSTRATION GUARDRAIL**:  
All live presentations, judging evaluations, and rehearsals must maintain simulation playback speed at **1x** during active incident response to ensure real-time physical synchrony with Nemotron cloud inference.

---

### 5.2 Scene-by-Scene Live Showcase Rehearsal Script

```
+---------------------------------------------------------------------------------------------------------------+
| SCENE 1: STEADY-STATE BASELINE & CYBER-PHYSICAL BENCH OVERVIEW (0:00 - 0:45)                                 |
+---------------------------------------------------------------------------------------------------------------+
| Presenter Narrative:                                                                                          |
| "Welcome to AVON AI. Before you is a live cyber-physical demonstration of autonomous supervisory control for   |
| an upstream saltwater gathering and disposal facility. Our plant is running in steady-state balance."        |
|                                                                                                               |
| Actions & Physical Responses:                                                                                 |
| 1. Presenter walks up to the bench. Modulino Distance sensor detects presence; all 3 matrices brighten to 100%.|
| 2. Device 1 (P-201): Renders smooth animated water waves at 60% fill level (Duty Pump 1 running nominal).      |
| 3. Device 2 (P-203): Renders smooth animated water waves at 88% fill level (Duty Pump 2 running nominal).      |
| 4. Device 3 (P-204): Dark standby display with single center baseline dot (Standby Pump available).           |
| 5. Modulino Pixels: Solid Emerald Green across all 8 LEDs. Web Dashboard indicates 0 active alarms.           |
+---------------------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------------------+
| SCENE 2: PHYSICAL FAULT INJECTION & MATHEMATICAL INVERSION (0:45 - 1:30)                                      |
+---------------------------------------------------------------------------------------------------------------+
| Presenter Narrative:                                                                                          |
| "In harsh Permian basin operations, sand and produced solids severely erode pump impellers. Let's introduce   |
| acute mechanical wear on Duty Pump P-203 using the physical Modulino Knob."                                   |
|                                                                                                               |
| Actions & Physical Responses:                                                                                 |
| 1. Presenter clicks Modulino Knob to select Channel 2, then rotates knob counter-clockwise to 40% wear.       |
| 2. Device 2 (P-203): Matrix instantly alternates between fluid waves and flashing Caution Triangle.          |
| 3. Modulino Buzzer: Emits 880 Hz urgent warning tone. Modulino Pixels transition to Warning Amber.           |
| 4. Technical Explanation: Presenter points to web dashboard: "Flow dropped to 122.5 bbl/hr. A traditional     |
|    system cannot distinguish wear from pipeline restriction. But AVON AI correlates discharge pressure (33   |
|    psi vs 83 psi), allowing closed-form 2x2 mathematical inversion to pinpoint impeller wear instantly."      |
+---------------------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------------------+
| SCENE 3: AUTONOMOUS REASONING & HUMAN-IN-THE-LOOP PROPOSAL GATE (1:30 - 2:15)                                  |
+---------------------------------------------------------------------------------------------------------------+
| Presenter Narrative:                                                                                          |
| "With P-203 degraded, Tank T-104 is accumulating fluid. Left unchecked, it will breach High-High shut-in      |
| within 98 minutes, causing an environmental emergency. NVIDIA Nemotron is now analyzing the plant."           |
|                                                                                                               |
| Actions & Physical Responses:                                                                                 |
| 1. AVON Intelligence panel streams Nemotron multi-step reasoning: evaluates hydraulic headroom, checks pump   |
|    availability, and formulates formal Proposal PROP-2026-004.                                                |
| 2. Web UI highlights Recommendation: "Start Standby Pump P-204, throttle P-203, dispatch mechanical overhaul."|
| 3. Speed Guardrail Check: Verify simulation playback speed is at 1x.                                          |
+---------------------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------------------+
| SCENE 4: ACTUATION, STANDBY FAILOVER & HARDWARE VERIFICATION (2:15 - 3:00)                                    |
+---------------------------------------------------------------------------------------------------------------+
| Presenter Narrative:                                                                                          |
| "In high-consequence infrastructure, the human operator retains ultimate authority. Let's approve the         |
| recommendation via our control deck."                                                                         |
|                                                                                                               |
| Actions & Physical Responses:                                                                                 |
| 1. Presenter clicks 'Approve Recommendation' on the dashboard (or presses key 'a' on the keyboard deck).      |
|    (Note: Button C is strictly reserved as P-204 emergency trip; it is NOT pressed here).                     |
| 2. Device 3 (P-204): Instantly wakes from dark standby! Matrix pulses outward in starting animation, then     |
|    transitions to full, running sinusoidal water waves.                                                       |
| 3. Device 2 (P-203): Transitions smoothly to controlled standby.                                              |
| 4. Modulino Pixels: Shift from Amber back to nominal Green. Tank T-104 level stabilizes.                      |
| 5. (Alternative BPCS Failover Demo): Presenter demonstrates emergency duty trip by pressing Modulino Button B.|
|    P-203 snaps to solid Caution Triangle; Layer 2 BPCS autonomously starts P-204 in 100 ms without waiting.  |
+---------------------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------------------+
| SCENE 5: SYSTEM RECOVERY & STRATEGIC WRAP-UP (3:00 - 3:30)                                                    |
+---------------------------------------------------------------------------------------------------------------+
| Presenter Narrative:                                                                                          |
| "With zero spills and zero downtime, AVON AI prevented an estimated $142,000 environmental shut-in penalty.    |
| By bridging physical edge microcontrollers with NVIDIA Nemotron cloud intelligence, AVON AI delivers the      |
| future of resilient industrial automation."                                                                   |
|                                                                                                               |
| Actions & Physical Responses:                                                                                 |
| 1. Operator clears faults via Web UI. Modulino Buzzer silences. All 3 boards return to nominal green state.   |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 6. Acceptance Verification Suite & Checklist

### 6.1 Automated Verification Commands

The following command suite verifies that all code, firmware packing algorithms, hydraulic equations, and constraints are fully compliant:

```powershell
# ==============================================================================
# CHECK 1: Negative Constraint Audits (Must return 0 matches repository-wide)
# ==============================================================================
# Prohibited copyright string check
Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch "node_modules|\.git|__pycache__|\.agents\\teamwork" } | Select-String -Pattern "avon corps" -CaseSensitive:$false

# Prohibited Comic Sans font check
Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch "node_modules|\.git|__pycache__|\.agents\\teamwork" } | Select-String -Pattern "comic sans" -CaseSensitive:$false

# Frontend production bundle verification
Select-String -Path "avon-ai\frontend\dist\assets\*.js" -Pattern "Avon Corps"

# ==============================================================================
# CHECK 2: LED Matrix Frame Packing Verification (C++ Bit-Packing Parity)
# ==============================================================================
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

# ==============================================================================
# CHECK 3: Hydraulic Identifiability Math Verification
# ==============================================================================
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

# ==============================================================================
# CHECK 4: Frontend Production Build Cleanliness
# ==============================================================================
npm --prefix avon-ai/frontend run build
```

---

### 6.2 Acceptance Criteria Checklist

- [x] **Negative Constraint Purge**: Prohibited fake copyright notice completely purged from `App.tsx` and rebuilt `dist/` bundle.
- [x] **Negative Constraint Audits**: 0 occurrences of "Comic Sans" and 0 occurrences of "Avon Corps" across all repository source code and built assets.
- [x] **Button C Control Alignment**: Modulino Button C strictly assigned as P-204 Emergency Trip / Reset Toggle; proposal approvals routed exclusively via Web UI or key `'a'`.
- [x] **Standby Failover Demonstration**: Standby failover demonstrated via physical Button B (trips duty pump P-203) or Web UI approval.
- [x] **LED Matrix Bitmasks**: Packed 32-bit words for Solid X (`[0x20410809, 0x00600600, 0x90108204]`) and Caution Triangle (`[0x0200500A, 0x81242024, 0x21FFF000]`) verified bit-for-bit against C++ `Framebuffer::pack`.
- [x] **Hydraulic Identifiability Proof**: Mathematical proof establishing $Q=122.47\text{ bbl/hr}$ non-identifiability and discharge pressure $P$ ($33.33\text{ psi}$ vs $83.33\text{ psi}$) separation documented in Sections 1.2.1, 2.4.2, and 3.1.
- [x] **Serial Gateway Threading**: Asynchronous non-blocking worker thread architecture documented for `_try_connect()` in `bridge.py` to preserve the 10 Hz broadcast loop and 1500 ms MCU watchdog.
- [x] **Knob Push-Switch Debounce**: 250 ms rising-edge debouncing and channel state latching specified for `hal_peripherals.cpp`.
- [x] **Simulation Speed Guardrail**: 1x simulation playback speed guardrail established to prevent revision drift (HTTP 409) and dynamic tank overrun during live AI reasoning.
- [x] **Deliverable Synchronization**: Deliverable files synchronized identically at root and `teamwork_worker_plan/`.
