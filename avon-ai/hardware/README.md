# AVON AI — Hardware Integration & Edge Subsystem (5-Node Visualizer Network)

This directory contains the serial gateway, operator control deck, and PlatformIO embedded firmware for integrating **5 physical Arduino UNO R4 WiFi** microcontrollers with 12×8 LED matrices into the **AVON AI** produced-water network.

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

## Directory Structure

```
hardware/
  README.md                     # This documentation
  PROTOCOL.md                   # Packet specifications and handoff docs for Person B
  requirements-hw.txt           # Python dependencies (pyserial, websockets, requests, colorama)

  firmware/                     # PlatformIO firmware project for the 5 Arduino UNO R4s
    platformio.ini              # Multi-target build configuration (device 1..5)
    include/
      protocol.h                # C/C++ packet structs & parser matching PROTOCOL.md
    src/
      main.cpp                  # Modular firmware with 5 asset renderers & fallback demo

  gateway/                      # Software running on your computer
    bridge.py                   # High-performance WebSocket-to-5x-Serial dispatcher
    control_deck.py             # Computer keyboard control deck (Trip, Degrade, Approve, Reset)
    config.json                 # COM port assignments and network endpoints

  tools/                        # Testing & Benchmarking tools
    test_feeder.py              # Interactive CLI to send mock telemetry to any of the 5 Arduinos
    mock_serial_bridge.py       # Virtual serial loopback emulator for off-hardware testing
```

---

## How to Flash the 5 Arduinos with PlatformIO

Plug an Arduino UNO R4 into your computer via USB-C, navigate to `hardware/firmware`, and flash the appropriate profile:

```powershell
cd avon-ai/hardware/firmware

# Flash Device 1 (Tank T-104)
pio run -e uno_r4_device1 -t upload

# Flash Device 2 (Pipeline PL-1)
pio run -e uno_r4_device2 -t upload

# Flash Device 3 (Treatment Facility TRT-1)
pio run -e uno_r4_device3 -t upload

# Flash Device 4 (Tank T-101)
pio run -e uno_r4_device4 -t upload

# Flash Device 5 (Pipeline PL-2)
pio run -e uno_r4_device5 -t upload
```

*(Note: If `pio` is not in your PATH, run `& "$HOME\.platformio\penv\Scripts\pio.exe"`)*

---

## How to Run the Full Live System

### Step 1: Start AVON AI Backend & Frontend (on your computer)
```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

### Step 2: Plug in the 5 Arduinos
Plug the 5 Arduinos into your computer's USB ports (or a powered USB hub).
Check their COM ports in [`gateway/config.json`](file:///c:/Users/avisi/Documents/GitHub/AvonAI-SecondPass/avon-ai/hardware/gateway/config.json) (e.g. `COM3` through `COM7`).

### Step 3: Start the Gateway Bridge
```powershell
python hardware/gateway/bridge.py --config hardware/gateway/config.json
```
*(The bridge automatically connects to all 5 boards and starts streaming live plant data).*

### Step 4: Open the Control Deck
In another terminal, run:
```powershell
python hardware/gateway/control_deck.py
```
- Press `t` to trip P-203 duty pump (Layer 2 auto-starts standby P-204).
- Press `d` to degrade P-203 to 45% (AVON AI recommends starting P-204).
- Press `a` to **Approve** the recommendation.
- Press `c` to constrain Treatment TRT-1 to 50% (both pipelines throttle).

---

## Person B Testing Tool

Person B can test any animation on their desk without the simulation running:
```powershell
python hardware/tools/test_feeder.py --port COM3 --device 2 --interactive
```
Press `+` and `-` to raise and lower fluid flow and watch the 12×8 matrix speed adjust live.
