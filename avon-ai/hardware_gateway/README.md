# AVON AI — Hardware Gateway & Edge Control Subsystem (5-Node Visualizer Network)

This directory contains the fault-tolerant serial gateway, operator control deck, and developer tools for connecting **5 physical Arduino UNO R4 WiFi** microcontrollers with 12×8 LED matrices to the **AVON AI** produced-water network.

All controls and the display kiosk run directly on the host computer.

---

## Physical Network Layout (The Presentation Table)

The 5 Arduinos map directly to the plant network topology:

```
[ Arduino #4: Tank T-101 & P-201 ] ===> [ Arduino #5: Pipeline PL-2 ] ──┐
                                                                        ├──> [ Arduino #3: Treatment TRT-1 ]
[ Arduino #1: Tank T-104 & Pumps ] ===> [ Arduino #2: Pipeline PL-1 ] ──┘
```

| Unit | Plant Asset | Matrix Visual Function |
|---|---|---|
| **Arduino #1** | **Tank T-104 & Pumps (P-203/P-204)** | Level fill bar (0–1000 bbl), H/HH alarms, duty/standby pump status |
| **Arduino #2** | **Pipeline PL-1** | Dynamic fluid flow wave (speed $\propto$ PL-1 flow 0–250 bbl/hr) |
| **Arduino #3** | **Treatment TRT-1** | Swirling intake vortex (0–400 bbl/hr) & backpressure constraint alert |
| **Arduino #4** | **Tank T-101 & Pump P-201** | Level fill bar (0–1000 bbl), H/HH alarms, P-201 pump status |
| **Arduino #5** | **Pipeline PL-2** | Dynamic fluid flow wave (speed $\propto$ PL-2 flow 0–250 bbl/hr) |

---

## Physical Fault Tolerance (Hot-Plug & Disconnect Resilience)

Industrial plants cannot afford for one peripheral bus failure to stall the entire plant. `bridge.py` implements:
1. **Per-Channel Isolation:** Each Arduino has its own independent serial channel. If an Arduino is unplugged mid-run, its write error is caught immediately without blocking or lagging the other 4 Arduinos.
2. **Non-Blocking Auto-Reconnect:** When an unplugged Arduino is reconnected to USB, the gateway automatically discovers and rebinds to it within 3 seconds, resuming real-time telemetry.
3. **Firmware Autonomous Fallback:** If an Arduino is severed from serial data, its firmware falls back to an autonomous local display mode so the matrix never freezes into an unreadable state.

---

## Directory Structure

```
hardware_gateway/
  bridge.py                   # Fault-tolerant WebSocket-to-5x-Serial dispatcher
  control_deck.py             # Computer keyboard control deck (Trip, Degrade, Approve, Reset)
  config.json                 # COM port assignments and network endpoints
  PROTOCOL.md                 # Packet specification (Manas v1 contract compatible)
  README.md                   # This documentation
  requirements-hw.txt         # Dependencies (pyserial, websockets, requests, colorama)

  tools/                      # Developer testing tools
    test_feeder.py            # Standalone CLI feeder to test any of the 5 matrices
    mock_serial_bridge.py     # Virtual serial loopback monitor

  firmware_reference/         # PlatformIO reference firmware scaffold
```

---

## How to Run the Demo on Your Computer

### Step 1: Start AVON AI Backend & Frontend (on your computer)
```powershell
# Terminal 1: Backend
cd avon-ai\backend
py -m uvicorn app.main:app --port 8080

# Terminal 2: Frontend (Kiosk view in your browser @ http://localhost:5173)
cd avon-ai\frontend
npm run dev
```

### Step 2: Plug in the 5 Arduinos
Plug the 5 Arduinos into your computer's USB ports (or a USB hub).
Check their COM ports in [`hardware_gateway/config.json`](config.json) (e.g. `COM3` through `COM7`).

### Step 3: Start the Gateway Bridge
```powershell
cd avon-ai
py hardware_gateway/bridge.py --config hardware_gateway/config.json
```
*(Add `--dry-run` to test before plugging in Arduinos).*

### Step 4: Open the Operator Control Deck
In another terminal, run:
```powershell
cd avon-ai
py hardware_gateway/control_deck.py
```
- Press `t` to trip P-203 duty pump (Layer 2 auto-starts standby P-204).
- Press `d` to degrade P-203 to 45% (AVON AI recommends starting P-204).
- Press `a` to **Approve** the recommendation.
- Press `c` to constrain Treatment TRT-1 to 50% (both pipelines throttle).
