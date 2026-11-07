# AVON AI — Hardware Gateway & Edge Subsystem (5-Pump Network)

This directory contains the fault-tolerant serial gateway, operator control deck, and developer tools for connecting **5 physical Arduino UNO R4 WiFi** microcontrollers with 12×8 LED matrices acting as **active physical pumps** in the **AVON AI** produced-water network.

All controls and the display kiosk run directly on the host computer.

---

## Physical Network Layout (The 5 Physical Pumps)

Each Arduino represents a physical pump on the presentation table:

```
[ P-SRC1: Arduino #4 ] ──> (Tank T-104) ──> [ P-203 Duty: Arduino #1 ] ──┐
                                       └──> [ P-204 Sby:  Arduino #2 ] ──┼──> (Treatment)
[ P-SRC2: Arduino #5 ] ──> (Tank T-101) ──> [ P-201 Duty: Arduino #3 ] ──┘
```

| Arduino Unit | Pump Tag | Role | Plant Subsystem |
|---|---|---|---|
| **Arduino #1** | **P-203** | Primary Duty Outflow Pump | Tank T-104 $\rightarrow$ Pipeline PL-1 |
| **Arduino #2** | **P-204** | Redundant Standby Pump | Tank T-104 (Auto-changeover standby) |
| **Arduino #3** | **P-201** | Primary Duty Outflow Pump | Tank T-101 $\rightarrow$ Pipeline PL-2 |
| **Arduino #4** | **P-SRC1** | Wellhead Inflow Lift Pump 1 | Wellhead Source 1 $\rightarrow$ Tank T-104 (HH Shut-in) |
| **Arduino #5** | **P-SRC2** | Wellhead Inflow Lift Pump 2 | Wellhead Source 2 $\rightarrow$ Tank T-101 (HH Shut-in) |

---

## 12×8 LED Matrix Pump Animations

Each Arduino displays:
1. **Suction Pipe (Left):** Water particles streaming into the pump casing.
2. **Impeller Rotor (Center):** 
   - **RUNNING:** Fast, smooth 4-frame rotating impeller vanes.
   - **DEGRADED:** Slow, labored rotation (indicating cavitation / wear).
   - **STARTING:** Pulsing center hub during auto-start delay.
   - **TRIPPED:** Large flashing red `X` with stationary impeller.
   - **STOPPED:** Idle baseline cross.
3. **Discharge Pipe (Right):** Water surging out at speed directly proportional to `flow_bbl_hr`.

---

## Physical Fault Tolerance (Disconnect & Hot-Plug Resilience)

- **Isolated Channels:** Each pump has its own independent serial port. If any Arduino is unplugged, the other 4 pumps keep running without a glitch.
- **Auto-Reconnect:** When plugged back in, the bridge rebinds automatically within 3 seconds.
- **Autonomous Fallback:** If disconnected from USB data, each board runs an autonomous demo pattern so the LED matrix never turns off or glitched.

---

## How to Flash the 5 Pumps with PlatformIO

Plug an Arduino into USB, navigate to `hardware_gateway/firmware_reference`:

```powershell
cd avon-ai\hardware_gateway\firmware_reference

# Flash Pump 1 (P-203 Duty)
pio run -e uno_r4_pump1 -t upload

# Flash Pump 2 (P-204 Standby)
pio run -e uno_r4_pump2 -t upload

# Flash Pump 3 (P-201 Duty)
pio run -e uno_r4_pump3 -t upload

# Flash Pump 4 (P-SRC1 Inflow 1)
pio run -e uno_r4_pump4 -t upload

# Flash Pump 5 (P-SRC2 Inflow 2)
pio run -e uno_r4_pump5 -t upload
```

---

## How to Run the Live System

### Step 1: Start AVON AI Backend & Frontend
```powershell
# Terminal 1: Backend
cd avon-ai\backend
py -m uvicorn app.main:app --port 8080

# Terminal 2: Frontend (Kiosk view in browser @ http://localhost:5173)
cd avon-ai\frontend
npm run dev
```

### Step 2: Start the Fault-Tolerant Bridge
```powershell
cd avon-ai
py hardware_gateway/bridge.py --config hardware_gateway/config.json
```
*(Add `--dry-run` to test before plugging in Arduinos).*

### Step 3: Open the Operator Control Deck
```powershell
cd avon-ai
py hardware_gateway/control_deck.py
```
- `t`: Trip P-203 duty pump (Watch Arduino 1 show 'X', then Arduino 2 standby auto-start after delay!).
- `d`: Degrade P-203 to 45% (Watch Arduino 1 impeller slow down).
- `a`: **Approve** recommendation (Watch Arduino 2 spin up to full capacity).
