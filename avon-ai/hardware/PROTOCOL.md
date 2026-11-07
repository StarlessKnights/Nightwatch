# AVON AI — Hardware Serial Protocol Specification (5-Device Network)

This document defines the serial communication protocol between the **Computer Host Gateway** and the **5 Arduino UNO R4 WiFi** microcontrollers driving the 12×8 LED matrices.

---

## 1. Network Topology & Physical Allocation

The 5 Arduinos represent the complete produced-water network arranged on the demo table:

```
[ Device 4: Tank T-101 & P-201 ] ===> [ Device 5: Pipeline PL-2 ] ──┐
                                                                    ├──> [ Device 3: Treatment TRT-1 ]
[ Device 1: Tank T-104 & Pumps ] ===> [ Device 2: Pipeline PL-1 ] ──┘
```

| Device ID | Plant Asset | Matrix Visual Function |
|---|---|---|
| **Device 1** | **Tank T-104 & P-203/P-204** | Tank level bar (0–1000 bbl), H/HH alarms, duty/standby pump status |
| **Device 2** | **Pipeline PL-1** | Upper waterflow animation (speed $\propto$ PL-1 flow 0–250 bbl/hr) |
| **Device 3** | **Treatment TRT-1** | Combined processing intake vortex & backpressure alert (0–400 bbl/hr) |
| **Device 4** | **Tank T-101 & P-201** | Tank level bar (0–1000 bbl), H/HH alarms, P-201 pump status |
| **Device 5** | **Pipeline PL-2** | Lower waterflow animation (speed $\propto$ PL-2 flow 0–250 bbl/hr) |

---

## 2. Physical & Serial Parameters

- **Interface:** USB CDC Serial (e.g. `COM3`..`COM7` on Windows; `/dev/ttyACM0`..`/dev/ttyACM4` on Linux/macOS)
- **Baud Rate:** `115200`
- **Data Bits:** 8 | **Parity:** None | **Stop Bits:** 1
- **Framing:** One JSON object per line, terminated by newline (`\n`).
- **Update Frequency:** Dispatched every simulation tick (~5–10 Hz).

---

## 3. Packet Schemas (Computer $\rightarrow$ Arduinos)

### Device 1: Tank T-104 & Pumps P-203 (Duty) / P-204 (Standby)
```json
{
  "dev": 1,
  "lvl": 880.0,
  "cap": 1000.0,
  "inflow": 180.0,
  "outflow": 90.0,
  "p203": {"state": 1, "cf": 0.45, "label": "RUNNING"},
  "p204": {"state": 0, "cf": 1.0, "label": "STOPPED"},
  "alarm": 1,
  "interlock": 0
}
```

### Device 2: Pipeline PL-1 (Upper Fluid Flow Visualizer)
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

### Device 3: Treatment Facility TRT-1 (Central Intake & Backpressure Hub)
```json
{
  "dev": 3,
  "flow": 290.0,
  "cap": 400.0,
  "intake_factor": 1.0,
  "alarm": 0
}
```

### Device 4: Tank T-101 & Pump P-201
```json
{
  "dev": 4,
  "lvl": 650.0,
  "cap": 1000.0,
  "inflow": 200.0,
  "outflow": 200.0,
  "p201": {"state": 1, "cf": 1.0, "label": "RUNNING"},
  "alarm": 0,
  "interlock": 0
}
```

### Device 5: Pipeline PL-2 (Lower Fluid Flow Visualizer)
```json
{
  "dev": 5,
  "flow": 200.0,
  "cap": 250.0,
  "restr": 1.0,
  "dir": 1,
  "alarm": 0
}
```

---

## 4. Waterflow Animation Speed Mapping (Devices 2 & 5)

For the pipeline LED matrices:
$$ \text{frame\_delay\_ms} = \begin{cases} 
\text{No movement / static dashes} & \text{if } \text{flow} \le 1.0 \\
\text{clamp}\left(320 - \left(\frac{\text{flow}}{250.0} \times 280\right), 35, 320\right) & \text{if } \text{flow} > 1.0
\end{cases} $$

- **0 bbl/hr:** Static dashed line (flow stopped or pump tripped).
- **90 bbl/hr:** ~220 ms delay (slow trickle indicating pump degradation).
- **200 bbl/hr:** ~95 ms delay (steady, healthy waterflow).
- **250 bbl/hr:** ~40 ms delay (high velocity maximum flow).
