# AVON AI / Arduino Hardware Gateway Protocol Specification

## 1. Overview & Architecture

The Python Serial Gateway Bridge (`avon-ai/hardware_gateway/bridge.py`) connects the live simulation backend (FastAPI / WebSockets) to physical Arduino UNO R4 WiFi microcontrollers over USB CDC serial (115200 baud, 8-N-1).

The gateway operates in two primary modes:
- **v2 (NIGHTWATCH 3-Node Architecture)**: Dedicated specialized profiles for Tank (Node 1), Duty Pump (Node 2), and Output Stream & Security Killswitch (Node 3).
- **v1 (Legacy Multi-Pump Mode)**: Dedicated pump status for P-201, P-203, and P-204.

---

## 2. Boot & Handshake Protocol (`parse_hello`)

Upon power-up or when queried with `AVON|IDENTIFY\n`, each Arduino firmware emits a pipe-delimited greeting banner:

```
AVON|HELLO|v=<version>|dev=<dev_id>|profile=<profile>|fw=<firmware_ver>|caps=<capabilities>
```

### Handshake Regex Specification:
- **Protocol Versions**: Supports both `v=1` and `v=2`.
- **Device IDs (`dev`)**: `1`, `2`, `3`.
- **Profiles (`profile`)**:
  - v2 Profiles: `tank`, `pump`, `output`.
  - Legacy / Alternative Profiles: `cooling`, `triage`, `airgap`, `pipeline`, `treatment`.
- **Identity Routing**: The gateway uses the handshake banner to associate each COM port / serial link with its physical device ID and profile, regardless of the USB enumeration order.

---

## 3. Downstream 10 Hz Telemetry Extractor (v2 NIGHTWATCH)

The gateway broadcasts packets at **10 Hz (every 100 ms)** across all active serial links so embedded firmware watchdogs (`LINK_TIMEOUT_MS = 1500`) never expire. Each microcontroller filters packets by its compiled `dev` ID.

### Node 1: Tank (`dev: 1`)
Displays live tank level and capacity with water wave animations and high/low alarm alerts.
- **Data Source**: `current_state["tanks"]["HALL-A"]` (fallback: `"T-104"` / `"T-101"`).
- **Packet Format**:
  ```json
  {"v":2,"seq":101,"dev":1,"lvl":750,"cap":1000,"alarm":0}
  ```
- **Fields**:
  - `v`: Protocol version (`2`).
  - `seq`: Monotonically incrementing sequence number (0–65535).
  - `dev`: Device ID (`1`).
  - `lvl`: Current tank volume in barrels (integer).
  - `cap`: Total tank capacity in barrels (integer).
  - `alarm`: `0` for normal, `1` if an alarm is active on the tank or critical volume thresholds are reached (>95% or <5%).

### Node 2: Duty Pump (`dev: 2`)
Displays pump operational state, wear health factor, and live flow rate.
- **Data Source**: Duty pump `CHP-1` (fallback: `"P-203"` / `"P-201"`).
- **Packet Format**:
  ```json
  {"v":2,"seq":102,"dev":2,"state":1,"w":850,"flow":185.5}
  ```
- **Fields**:
  - `v`: Protocol version (`2`).
  - `seq`: Sequence number (0–65535).
  - `dev`: Device ID (`2`).
  - `state`: Operational state code:
    - `0`: Stopped / Idle
    - `1`: Running (healthy wear `w >= 500`)
    - `3`: Degraded (wear `w < 500`)
    - `4`: Tripped (fault active or tripped run-state)
  - `w`: Effective health/wear factor in thousandths (`0`–`1000`, where `1000` = 100%).
  - `flow`: Current pumped flow rate in bbl/hr (float).

### Node 3: Output Stream & Security (`dev: 3`)
Displays plant discharge rate, maximum intake limit, cyber incident airgap killswitch state, and discharge alarms.
- **Data Source**: Total loop/treatment discharge flow (`treatment` or `pipelines` in `current_state`), cyber incident state, and local airgap toggle.
- **Packet Format**:
  ```json
  {"v":2,"seq":103,"dev":3,"flow":330.0,"max_flow":400.0,"airgap":0,"alarm":0}
  ```
- **Fields**:
  - `v`: Protocol version (`2`).
  - `seq`: Sequence number (0–65535).
  - `dev`: Device ID (`3`).
  - `flow`: Current total discharge flow (float).
  - `max_flow`: Maximum rated treatment/pipeline capacity (float).
  - `airgap`: `0` when online; `1` when airgap killswitch is engaged (matrix displays security lockout pattern).
  - `alarm`: `0` when normal; `1` when airgap is engaged, flow exceeds `max_flow`, or a discharge alarm is active.

---

## 4. Upstream Event Routing (`rx_upstream_task`)

Upstream NDJSON packets sent from physical Arduinos are parsed and dispatched asynchronously to backend endpoints:

### 1. Modulino Rotary Knob (Wear / Throttle Control)
- **Source**: Node 2 (or any node with Modulino Knob).
- **Payload from Hardware**:
  ```json
  {"dev":2,"knob":750}
  ```
  or
  ```json
  {"dev":2,"event":"KNOB","val":750}
  ```
- **Gateway Action**: Scales knob reading from `0..1000` to `0.0..1.0` and dispatches `POST` to `/api/hardware/status`:
  ```json
  {"dev":2,"pump":"CHP-1","online":true,"knob":0.75,"telemetry":{...}}
  ```
- **Simulation Coupling**: Adjusts duty pump impeller wear health or speed throttling.

### 2. Airgap Killswitch (`AIRGAP_KILLSWITCH`)
- **Source**: Node 3 (Modulino Button A or dedicated safety switch).
- **Payload from Hardware**:
  ```json
  {"dev":3,"event":"AIRGAP_KILLSWITCH"}
  ```
- **Gateway Action**:
  1. Sends `POST` to `/api/incident/airgap`:
     ```json
     {"engaged": true, "source": "hardware_button_a"}
     ```
  2. Immediately toggles the gateway's local airgap flag (`local_airgap = 1`).
  3. Subsequent downstream 10 Hz telemetry packets for Node 3 immediately reflect `"airgap": 1` on the physical LED matrix.

### 3. Pump Trip & Reset (`PUMP_TRIP` / `TRIP_RESET`)
- **Source**: Node 3 (Modulino safety buttons).
- **Payload from Hardware**:
  - Trip: `{"dev":3,"event":"PUMP_TRIP"}`
  - Reset: `{"dev":3,"event":"TRIP_RESET"}`
- **Gateway Action**:
  - `PUMP_TRIP`: Calls `POST /api/faults` with `{"type": "PUMP_TRIP", "target": "CHP-1", "params": {"reason": "Modulino hardware button trip"}}`. Updates local pump state to `TRIPPED` (`state: 4`).
  - `TRIP_RESET`: Calls `DELETE /api/faults/{id}` to clear the trip fault on `CHP-1` (or `P-203`). Restores pump state to `RUNNING` (`state: 1`).

---

## 5. Legacy v1 Protocol Reference

For backwards compatibility with v1 firmware:
```json
{"v":1,"seq":1,"dev":1,"pump":"P-201","state":1,"w":1000,"available":1,"lvl":600,"cap":1000}
```
- State codes: `0` stopped, `1` running, `2` starting, `3` degraded, `4` tripped, `5` unavailable.
- Unavailable holds an X and takes priority over trips.
