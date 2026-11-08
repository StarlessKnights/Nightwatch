---
name: hil-serial-gateway
description: >-
  Troubleshooting and architectural guide for Hardware-in-the-Loop (HIL) serial gateways
  connecting Python / WebSocket backends to microcontrollers (Arduino, ESP32, Renesas).
  Activates when debugging serial ports, COM port dropouts, watchdog timeouts, or multi-board packet streaming.
---

# Hardware-in-the-Loop (HIL) Serial Gateway Runbook

This skill provides hardened patterns and diagnostics for bridging real-time software systems (FastAPI, WebSockets, web clients) to physical microcontrollers (e.g. Arduino UNO R4 WiFi, ESP32, STM32) over USB serial.

---

## 1. Core Architectural Invariants

### A. Decouple Serial Transmission Frequency from Backend Tick Rates
* **Problem**: Microcontroller firmware often enforces a watchdog timeout (e.g., `LINK_TIMEOUT_MS = 1500`) to detect lost connections. If the host Python gateway only transmits when a simulation tick or WebSocket frame arrives (e.g., 1 Hz, or paused during user inspection), the embedded watchdog will trip into an error or diagnostic mode (`...` dot pattern).
* **Rule**: Run an independent host telemetry transmission loop at **5 Hz to 10 Hz** (100 ms – 200 ms interval) in an asynchronous task. Cache the latest backend state in memory so the Arduinos are continuously fed with fresh packets even when the simulation clock is paused or stepping slowly.

### B. Fail Fast on Host Dependencies (No Silent Fallback)
* **Problem**: Wrapping `import serial` in a broad `try...except ImportError` and falling back to `--dry-run` causes the host to silently simulate serial writes in RAM while physical hardware sits idle in watchdog state.
* **Rule**: Validate host dependencies (`pyserial`, `websockets`) loudly at startup. Fail with an explicit error and install prompt:
  ```python
  try:
      import serial
      import serial.tools.list_ports
  except ImportError:
      sys.exit("Error: 'pyserial' is required. Install via: py -m pip install pyserial")
  ```

### C. Multi-Node Broadcast with Hardware Self-Filtering
* **Problem**: In multi-board setups, physical USB plugging order can arbitrarily swap COM ports (`COM4`, `COM5`, `COM6`), breaking fixed 1-to-1 port mappings (`device1 -> COM4`).
* **Rule**:
  1. Auto-discover all connected microcontrollers via `serial.tools.list_ports.comports()`.
  2. Broadcast packets for all active nodes (`dev: 1`, `dev: 2`, `dev: 3`) across all open serial links.
  3. Microcontroller firmware inspects `o["dev"] == DEVICE_ID` and drops foreign packets with `PARSE_IGNORED`, while accepting its own with `PARSE_VALID`.
  4. This eliminates port-guessing and makes cabling 100% plug-and-play.

### D. Per-Port Fault Isolation
* Write to each serial port in an isolated `try...except` block.
* If a board is unplugged or errors mid-stream:
  - Mark only that port as offline.
  - Close and clear its handle.
  - Set a backoff cooldown (e.g., 3.0s) before attempting to reconnect.
  - Never allow one port failure to block or delay writes to other active boards.

### E. Single Peripheral Multiplexing & Priority Telemetry Dispatch
* **Rotary Encoder Multiplexing**: When physical I/O controls fewer units than exist in the plant, use push-button encoder cycling (`modulinoKnob.isPressed()`) to cycle active channels (`P-1 -> P-2 -> P-3`). Store state in a local channel array (`pumpKnobPos[4]`) so channel switches preserve individual settings. Provide multi-sensory feedback (LED matrix overlay, buzzer chime, RGB pixels).
* **Button Edge Detection**: For safety/trip buttons (`ModulinoButtons`), sample at 20 Hz, detect rising edges (`btn && !lastBtn`), and trigger immediate transmission (`due = true`) instead of waiting for periodic heartbeats.

### F. Multi-Board Identity Collisions
* If an Arduino displays its watchdog timeout diagnostic (`...`), check the gateway logs for duplicate identity collisions (`Links: [COM4:D2 COM5:D2 COM6:OFF]`).
* Remedy by flashing explicit environments to target ports:
  ```powershell
  pio run -d avon-ai/hardware -e uno_r4_pump1 -t upload --upload-port COM6
  pio run -d avon-ai/hardware -e uno_r4_pump2 -t upload --upload-port COM5
  pio run -d avon-ai/hardware -e uno_r4_pump3 -t upload --upload-port COM4
  ```

### G. Standby Pump Reconnection Safeguards
* When microcontrollers reconnect, restore `available = True` and `hardware_online = True`.
* NEVER auto-start standby/backup pumps into `RUNNING`; they must remain `STOPPED` until called by auto-changeover or operator command.

---

## 2. Diagnostic & Probing Toolchain

### Quick Serial Port Discovery (PowerShell)
```powershell
# List all active USB COM ports with hardware IDs
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Caption -match "COM\d+" } | Select-Object Caption, DeviceID
```

### Python Rapid Port Probe
Run this one-liner to verify port accessibility and installed packages:
```powershell
py -c "import serial.tools.list_ports; print([(p.device, p.description, p.hwid) for p in serial.tools.list_ports.comports()])"
```

### USB CDC Touch Reset
On Renesas RA4M1 / SAMD USB CDC microcontrollers, traditional DTR toggles may not trigger a reset. To trigger bootloader reset:
```python
import serial
s = serial.Serial('COM4', 1200)
s.close() # 1200 bps touch triggers software reset
```

---

## 3. Protocol Packet Invariants
When serializing NDJSON:
1. Use compact formatting: `json.dumps(payload, separators=(',', ':')) + '\n'`.
2. Keep maximum line length under the microcontroller's `INPUT_LINE_MAX` buffer (typically 192 or 256 bytes).
3. Transmit integers for scaling factors (e.g. `w: 1000` for 1.000) to prevent floating-point parsing overhead on 8-bit/32-bit MCUs.
