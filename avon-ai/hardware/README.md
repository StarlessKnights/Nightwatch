# AVON AI — Hardware Integration & Edge Subsystem

This directory contains the edge gateway, physical controls, kiosk setup, and PlatformIO embedded firmware for integrating physical hardware into the **AVON AI** produced-water network.

---

## Hardware Inventory & Architecture

| Hardware Unit | Role | OS / Framework | Key Responsibility |
|---|---|---|---|
| **Raspberry Pi 5** | Industrial Edge Gateway & SCADA Controller | Raspberry Pi OS (64-bit Bookworm) | Runs `bridge.py` (WS $\leftrightarrow$ Serial), `gpio_controller.py` (physical switches/buttons), safety interlock edge monitor. |
| **Raspberry Pi 3** | Operator Kiosk / Terminal | Raspberry Pi OS (32/64-bit) | Dedicated HMI console running Chromium fullscreen kiosk to the AVON AI React frontend. |
| **Arduino UNO R4 #1** | Tank T-104 & Pump Station Display | PlatformIO (Arduino Renesas RA4M1) | 12×8 LED Matrix: Tank level bar graph (0–1000 bbl), H/HH alarms, duty/standby pump status. |
| **Arduino UNO R4 #2** | Pipeline PL-1 Waterflow Visualizer | PlatformIO (Arduino Renesas RA4M1) | 12×8 LED Matrix: Dynamic cascading waterflow ripples with frame rate proportional to `flow.py` bbl/hr. |
| **Arduino UNO R4 #3** | Treatment Facility TRT-1 & Inflow Hub | PlatformIO (Arduino Renesas RA4M1) | 12×8 LED Matrix: Treatment intake whirlpool/processing animation, backpressure throttling alert. |

```
                       PHYSICAL DATA FLOW ARCHITECTURE
                       
    [ Central Sim Backend ] (FastAPI @ :8000)
              │
              │ WebSocket (/ws/sim) & REST (/api)
              ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                       RASPBERRY PI 5                            │
   │                                                                 │
   │  ┌────────────────────────┐      ┌───────────────────────────┐  │
   │  │   bridge.py            │◄────►│   gpio_controller.py      │  │
   │  │   (WebSocket Client &  │      │   (Physical E-Stop,       │  │
   │  │    Serial Dispatcher)  │      │    Degrade Dial, Approve) │  │
   │  └───────────┬────────────┘      └───────────────────────────┘  │
   └──────────────┼──────────────────────────────────────────────────┘
                  │ 3× USB Serial links @ 115200 baud
      ┌───────────┼───────────┐
      ▼           ▼           ▼
 ┌─────────┐ ┌─────────┐ ┌─────────┐                ┌─────────────────┐
 │ Arduino │ │ Arduino │ │ Arduino │                │ RASPBERRY PI 3  │
 │ UNO R4  │ │ UNO R4  │ │ UNO R4  │                │                 │
 │ Unit #1 │ │ Unit #2 │ │ Unit #3 │                │ Chromium Kiosk  │
 │ (Tank)  │ │ (Pipe)  │ │ (Trt)   │                │ (React HMI UI)  │
 └─────────┘ └─────────┘ └─────────┘                └─────────────────┘
```

---

## Directory Structure

```
hardware/
  README.md                     # This documentation
  PROTOCOL.md                   # Packet specifications and handoff docs for Person B
  requirements-hw.txt           # Python dependencies (pyserial, websockets, requests, gpiozero, etc.)
  setup_pi.sh                   # Automated deployment script for Raspberry Pi 5 & 3

  firmware/                     # PlatformIO firmware project for Arduino UNO R4s
    platformio.ini              # Multi-target build configuration (device 1, 2, 3)
    include/
      protocol.h                # C/C++ packet structs & parser matching PROTOCOL.md
    src/
      main.cpp                  # Modular firmware with non-blocking serial parser & role handlers
    lib/                        # Custom animation & matrix helper libraries

  gateway/                      # Software running on Raspberry Pi 5
    bridge.py                   # High-performance WebSocket-to-Serial dispatcher
    gpio_controller.py          # Physical hardware switches, buttons, and status LEDs
    config.json                 # Ports, pinout mapping, and network endpoints
    systemd/
      avon-gateway.service      # Systemd service for auto-start on boot

  kiosk/                        # Software running on Raspberry Pi 3
    kiosk.sh                    # Low-overhead Chromium kiosk script (tuned for 1GB RAM)
    systemd/
      avon-kiosk.service        # Systemd service for auto-start on boot

  tools/                        # Testing & Benchmarking tools
    test_feeder.py              # Interactive CLI to send mock telemetry to Arduinos
    mock_serial_bridge.py       # Virtual serial loopback emulator for off-hardware testing
```

---

## Quickstart

### 1. Developer Machine (Testing without hardware)
Test the serial packets in interactive simulation mode:
```bash
# Run the interactive feeder (supports keyboard shortcuts to test animations)
python hardware/tools/test_feeder.py --interactive
```

### 2. Raspberry Pi 5 Setup (Edge Gateway & Controls)
```bash
cd hardware
bash setup_pi.sh --role gateway

# Start manually or via systemd
python3 gateway/bridge.py --config gateway/config.json
```

### 3. Raspberry Pi 3 Setup (Operator Kiosk)
```bash
cd hardware
bash setup_pi.sh --role kiosk

# Launch the kiosk browser (points to Pi 5 or server IP)
bash kiosk/kiosk.sh http://<PI5_IP>:5173
```

### 4. Flashing Arduino UNO R4s with PlatformIO
Open `hardware/firmware` in VS Code with PlatformIO IDE installed, or use the PlatformIO CLI:
```bash
cd hardware/firmware

# Flash Device 1 (Tank T-104)
pio run -e uno_r4_device1 --target upload

# Flash Device 2 (Pipeline PL-1)
pio run -e uno_r4_device2 --target upload

# Flash Device 3 (Treatment Facility TRT-1)
pio run -e uno_r4_device3 --target upload
```
