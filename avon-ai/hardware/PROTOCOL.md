# AVON AI — Hardware Serial Protocol Specification

This document defines the serial communication protocol between the **Raspberry Pi 5 Gateway** and the **3 Arduino UNO R4 WiFi** microcontrollers driving the 12×8 LED matrices.

---

## 1. Physical & Serial Parameters

- **Interface:** USB CDC Serial (`/dev/ttyACM0`, `/dev/ttyACM1`, `/dev/ttyACM2` on Linux; `COMx` on Windows)
- **Baud Rate:** `115200`
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **Flow Control:** None
- **Framing:** One JSON object per line, terminated by newline (`\n` or `\r\n`).
- **Update Frequency:** Dispatched on every simulation tick (~10 Hz max, nominal 1–5 Hz depending on playback speed).

---

## 2. Packet Schemas (Gateway $\rightarrow$ Arduinos)

Each packet includes a `"dev"` identifier field (`1`, `2`, or `3`). Microcontrollers filter on this field or accept pre-filtered streams assigned to their specific USB port.

### Device 1: Tank T-104 & Pump Station (P-203 Duty / P-204 Standby)
Provides the live tank level, flow balance, and operational states for the pumps.

```json
{
  "dev": 1,
  "lvl": 880.0,
  "cap": 1000.0,
  "inflow": 180.0,
  "outflow": 90.0,
  "p203": {
    "state": 1,
    "cf": 0.45,
    "label": "RUNNING"
  },
  "p204": {
    "state": 0,
    "cf": 1.0,
    "label": "STOPPED"
  },
  "alarm": 1,
  "interlock": 0
}
```

#### Fields Description:
- `lvl` (*float*): Reported liquid volume in barrels (0.0 to 1000.0 bbl).
- `cap` (*float*): Tank capacity (typically 1000.0 bbl).
- `inflow` (*float*): Total incoming flow rate (bbl/hr).
- `outflow` (*float*): Total outgoing pump flow rate (bbl/hr).
- `p203` / `p204`:
  - `state` (*int*):
    - `0` = STOPPED / STANDBY
    - `1` = RUNNING
    - `2` = TRIPPED
    - `3` = STARTING
  - `cf` (*float*): Effective capacity factor (1.0 = normal, 0.45 = degraded, 0.0 = offline).
  - `label` (*string*): Human-readable state string for debug.
- `alarm` (*int*):
  - `0` = NORMAL (below H limit)
  - `1` = HIGH (lvl $\ge$ 900 bbl)
  - `2` = HIGH-HIGH / CRITICAL (lvl $\ge$ 950 bbl)
- `interlock` (*int*): `1` if safety interlock has shut in inflow, `0` otherwise.

---

### Device 2: Pipeline PL-1 (Waterflow Visualizer)
Controls the dynamic water animation across the 12×8 LED matrix.

```json
{
  "dev": 2,
  "flow": 90.0,
  "cap": 250.0,
  "restr": 1.0,
  "dir": 1,
  "alarm": 0
}
```

#### Fields Description:
- `flow` (*float*): Real-time fluid throughput in bbl/hr (0.0 to 250.0).
- `cap` (*float*): Maximum pipeline physical throughput (250.0 bbl/hr).
- `restr` (*float*): Restriction factor (1.0 = clear, < 1.0 = restricted / bottleneck).
- `dir` (*int*): Flow direction (`1` = forward T-104 $\rightarrow$ TRT-1, `0` = halted / static, `-1` = backpressure).
- `alarm` (*int*): `1` if pipeline restriction fault is active, `0` otherwise.

---

### Device 3: Treatment Facility TRT-1 & Inflow Hub
Displays intake processing vortex or backpressure accumulation.

```json
{
  "dev": 3,
  "flow": 180.0,
  "cap": 400.0,
  "intake_factor": 1.0,
  "alarm": 0
}
```

#### Fields Description:
- `flow` (*float*): Total intake processed by TRT-1 (bbl/hr).
- `cap` (*float*): Facility design capacity (400.0 bbl/hr).
- `intake_factor` (*float*): Active capacity fraction (0.5 during treatment constraint faults).
- `alarm` (*int*): `1` if treatment facility is operating under constraint or bottleneck.

---

## 3. Waterflow Animation Speed Mapping Guidelines

For Person B's animation engine on the 12×8 matrix:

$$ \text{frame\_delay\_ms} = \begin{cases} 
\infty \text{ (frozen / idle pattern)} & \text{if } \text{flow} \le 1.0 \\
\text{clamp}\left(350 - \left(\frac{\text{flow}}{250.0} \times 300\right), 35, 350\right) & \text{if } \text{flow} > 1.0
\end{cases} $$

### Key Animation Benchmarks:
| Flow Rate (bbl/hr) | Frame Delay | Visual Appearance |
|---|---|---|
| **0 bbl/hr (Tripped / Stopped)** | No scrolling | Static empty pipe line or pulsing red 'X' |
| **90 bbl/hr (Degraded P-203)** | ~240 ms | Slow, intermittent trickle droplets |
| **180 bbl/hr (Normal Run)** | ~130 ms | Steady, fluid chevron flow `> > >` |
| **200–250 bbl/hr (Full Standby / Flush)** | ~50 ms | Fast continuous cascading waves |

---

## 4. Reverse Communication (Arduino $\rightarrow$ Gateway)

Each Arduino may optionally emit status messages back to the Gateway for health monitoring or physical button presses:

```json
{"dev": 1, "type": "HEARTBEAT", "uptime_ms": 14200, "fps": 28}
{"dev": 2, "type": "ACK", "cmd": "SET_RATE"}
{"dev": 1, "type": "EVENT", "button": "MANUAL_TRIP"}
```
All messages from microcontrollers are automatically logged to the audit log by `bridge.py`.
