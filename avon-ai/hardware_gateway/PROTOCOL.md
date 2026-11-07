# AVON AI — Hardware Serial Protocol Specification (5-Pump Network)

All **5 Arduino UNO R4 WiFi** nodes act as **physical industrial pumps** in the synthetic produced-water network.

---

## 1. Physical Pump Assignment

| Device ID | Pump Tag | Role | Plant Location | Rated Capacity |
|---|---|---|---|---|
| **Device 1** | **P-203** | Primary Duty Outflow Pump | Tank T-104 $\rightarrow$ Pipeline PL-1 | 200 bbl/hr |
| **Device 2** | **P-204** | Redundant Standby Pump | Tank T-104 $\rightarrow$ Pipeline PL-1 (Auto-changeover) | 200 bbl/hr |
| **Device 3** | **P-201** | Primary Duty Outflow Pump | Tank T-101 $\rightarrow$ Pipeline PL-2 | 200 bbl/hr |
| **Device 4** | **P-SRC1** | Wellhead Inflow Lift Pump 1 | Wellhead Source 1 $\rightarrow$ Tank T-104 | 180 bbl/hr |
| **Device 5** | **P-SRC2** | Wellhead Inflow Lift Pump 2 | Wellhead Source 2 $\rightarrow$ Tank T-101 | 150 bbl/hr |

---

## 2. 12×8 LED Matrix Pump Graphics Specification

Each pump's matrix is divided into three functional zones:

```
  Cols 0..2 (Suction)        Cols 3..8 (Impeller / Volute)        Cols 9..11 (Discharge)
     Fluid flowing IN  ===>       Rotating Rotor / Impeller  ===>   Fluid surging OUT
```

### Visual States:
1. **RUNNING (state 1):**
   - Suction: Inflow particles `>` streaming into the pump.
   - Rotor: 4-frame rotating impeller spinning at high speed (delay ~45–120ms).
   - Discharge: Continuous fluid particles surging out at speed $\propto$ `flow_bbl_hr`.
2. **DEGRADED (state 3):**
   - Impeller rotates with labored, slower rotation (~180ms delay).
   - Discharge displays reduced trickle (e.g. 90 bbl/hr).
3. **STARTING (state 2):**
   - Center impeller hub pulses rhythmically during start delay before engaging.
4. **TRIPPED (state 4):**
   - Impeller is completely stationary.
   - Large flashing `X` overlays the pump casing.
   - Zero discharge flow.
5. **STOPPED / STANDBY (state 0):**
   - Stationary idle cross, empty discharge pipe.
6. **INTERLOCK SHUT-IN (il=1):**
   - Four corner strobe LEDs flash critical warning; pump halts immediately.

---

## 3. Serial Packet Contract (NDJSON, 115200 Baud)

Packets sent at 5–10 Hz matching Manas v1 protocol:

```json
{"v":1,"seq":120,"dev":1,"pump":"P-203","state":1,"flow":200,"max":200,"rf":1000,"lim":0,"al":0,"il":0}
{"v":1,"seq":121,"dev":2,"pump":"P-204","state":0,"flow":0,"max":200,"rf":1000,"lim":0,"al":0,"il":0}
{"v":1,"seq":122,"dev":3,"pump":"P-201","state":1,"flow":200,"max":200,"rf":1000,"lim":0,"al":0,"il":0}
{"v":1,"seq":123,"dev":4,"pump":"P-SRC1","state":1,"flow":180,"max":180,"rf":1000,"lim":0,"al":0,"il":0}
{"v":1,"seq":124,"dev":5,"pump":"P-SRC2","state":1,"flow":150,"max":150,"rf":1000,"lim":0,"al":0,"il":0}
```

### Fields:
- `v`: Protocol version (`1`).
- `seq`: Monotonically increasing sequence number (wraparound at 65536).
- `dev`: Target Arduino ID (`1` to `5`).
- `pump`: Plant tag (`"P-203"`, `"P-204"`, `"P-201"`, `"P-SRC1"`, `"P-SRC2"`).
- `state`:
  - `0`: STOPPED / Standby
  - `1`: RUNNING
  - `2`: STARTING
  - `3`: DEGRADED (wear / low flow)
  - `4`: TRIPPED (fault)
  - `5`: UNAVAILABLE (lockout)
- `flow`: Real-time throughput in bbl/hr.
- `max`: Rated design flow in bbl/hr.
- `rf`: Capacity factor in thousandths (`1000` = 1.0, `450` = 0.45).
- `lim`: Limiting bottleneck (`0`=none, `1`=pipeline, `2`=treatment, `3`=tank volume).
- `al`: Alarm severity (`0`=none, `1`=advisory, `2`=high, `3`=critical).
- `il`: Safety interlock shut-in (`1`=shut in, `0`=normal).
