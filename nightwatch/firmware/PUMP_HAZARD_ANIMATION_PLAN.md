# Dedicated pump hazard animation plan

This is a plan only. No implementation changes are included in this file.

## Hardware assignment

Each Arduino is a dedicated single-pump display. The existing tank, pipeline, and treatment profiles are superseded for this pump-only feature:

| Arduino device | Physical pump | Backend asset |
|---|---|---|
| Device 1 | Pump display 1 | `P-201` |
| Device 2 | Pump display 2 | `P-203` |
| Device 3 | Pump display 3 | `P-204` |

Every board has a matrix. No pump is routed to another board and no board renders another pump’s hazard.

## Scope

Each board responds only to the pump assigned to its `dev` ID. There are three direct pump triggers:

1. Pump trip: flashing caution triangle with an exclamation point.
2. Pump wear below 50%: flashing caution triangle with an exclamation point.
3. Pump unavailable: simple flashing `X`.

Tank volume, H/HH/LL alarms, tank interlocks, source shut-in, pipeline restrictions, treatment constraints, sensor faults, and generic alarm priority must not trigger these animations.

## Backend values

The backend exposes two health-like values:

- `eff_health` / `faults.Effective.pump_w`: simulated effective pump health `w`, where `1.0` is healthy and `0.0` is fully worn. This is the value for the wear threshold.
- `pumps[*].diagnosis.w_est`: inferred telemetry diagnosis. It may be `null` at low flow and must not drive the matrix trigger.

Use `eff_health < 0.50` as the strict wear condition. `0.50` does not trigger.

The pump state comes from `run_state` and availability:

- `RUNNING`: normal running state.
- `STARTING`: starting pulse.
- `STOPPED`: normal stopped/dash state unless `available=false`.
- `TRIPPED`: caution triangle.
- `available=false`: unavailable `X`, regardless of `run_state`.

Normal standby startup and normal standby auto-stop are ordinary pump lifecycle states. They do not create an `X` unless the backend marks the assigned pump unavailable.

## Per-device trigger rule

The Arduino evaluates only its assigned pump:

```text
if available == false or state == UNAVAILABLE:
    display solid X
else if state == TRIPPED:
    display solid caution triangle
else if effective_health < 0.50:
    alternate water waves and caution triangle
else:
    display water-level waves
```

Unavailable has priority over trip and wear. Clearing is automatic:

- `available=true` clears the X condition.
- Leaving `TRIPPED` clears the trip condition.
- Health `>= 0.50` clears the wear condition.
- When all three are clear, the normal pump animation returns.

There is no shared hazard latch. A P-201 condition changes only Device 1, P-203 only Device 2, and P-204 only Device 3.

## Serial contract

Replace the current zone-specific display packet with one common pump packet for all three devices:

```json
{"v":1,"seq":310,"dev":1,"pump":"P-201","state":1,"w":1000,"lvl":600,"cap":1000,"available":1}
{"v":1,"seq":311,"dev":2,"pump":"P-203","state":4,"w":299,"lvl":880,"cap":1000,"available":1}
{"v":1,"seq":312,"dev":3,"pump":"P-204","state":5,"w":1000,"lvl":600,"cap":1000,"available":0}
```

Fields:

- `v`: protocol version, initially 1.
- `seq`: gateway sequence number.
- `dev`: target Arduino, 1-3.
- `pump`: expected asset ID; the board rejects a packet whose pump does not match its device mapping.
- `state`: 0 stopped, 1 running, 2 starting, 3 degraded, 4 tripped, 5 unavailable.
- `w`: effective health in thousandths; `299` means `0.299`, `500` means `0.500`.
- `lvl` / `cap`: associated tank level and capacity used for the normal water-wave animation.
- `available`: effective availability, 0/1. `state=5` must also mean unavailable.

The gateway maps only from the assigned pump object:

```text
Device 1 -> state.pumps["P-201"]
Device 2 -> state.pumps["P-203"]
Device 3 -> state.pumps["P-204"]
```

No tank alarm, source, pipeline, treatment, or general alarm field is needed for the hazard trigger. The associated level is displayed only as normal water waves. Missing pump identity or a mismatched identity is rejected.

## Matrix visuals

Each board uses the whole 12x8 matrix for one pump.

### Normal states

- All non-hazard states: animated water waves filled from the bottom to `lvl / cap`, with a moving crest and occasional droplets.

### Caution triangle

When the assigned pump is worn below 50%, alternate every 400 ms between the normal water-wave frame and this warning triangle. A trip holds the triangle solid.

- Apex at row 0, column 6.
- Expanding outline through row 5.
- Full base on row 6.
- Exclamation lit at rows 2 and 3, dark at row 4, lit dot at row 5.

### Unavailable X

When the assigned pump is unavailable, show a solid simple full-size X:

- Diagonal from upper-left to lower-right.
- Diagonal from upper-right to lower-left.
- No triangle or tank alarm stripe.

## Firmware work items

1. Replace the Device 1 tank packet model with a common `PumpDisplayState` containing `pump`, `state`, `wear`, and `available`.
2. Compile each PlatformIO environment with a fixed device-to-pump mapping:

   - `device_tank` becomes Device 1 / P-201 pump display.
   - `device_pipeline` becomes Device 2 / P-203 pump display.
   - `device_treatment` becomes Device 3 / P-204 pump display.

3. Reject wrong-device and wrong-pump packets.
4. Implement pump-only trigger evaluation.
5. Reuse the approved triangle geometry and implement the simpler X animation.
6. Keep stale-link behavior per board: after 1.5 seconds without a valid packet, show the link-loss diagnostic instead of stale pump telemetry.
7. Keep the corner and API diagnostic environments unchanged for matrix validation.

## Gateway work items

1. Discover each board through its HELLO line.
2. Map board IDs to the fixed pump assignment.
3. Send complete pump packets at 5–10 Hz.
4. Send `eff_health`, not `diagnosis.w_est`.
5. Send `available=false` when the backend marks the pump unavailable.
6. Send `state=4` when the backend run state is `TRIPPED`.
7. Log the assigned pump ID, health, state, and availability beside each outbound packet.

## Test plan

Run the following tests independently on all three boards.

### Normal lifecycle

- [ ] Running: rotating vane.
- [ ] Starting: pulse.
- [ ] Stopped and available: dash/no hazard.
- [ ] Degraded at `w >= 0.50`: stuttering vane, no triangle.

### Wear boundary

- [ ] `w=510`, running: normal vane.
- [ ] `w=500`, running: normal vane; exact boundary does not trigger.
- [ ] `w=499`, running: flashing caution triangle.
- [x] `w=299`, stopped and available: alternating water waves and caution triangle.
- [x] Restore health to `w=500`: triangle clears.

### Trip

- [x] Healthy pump, `TRIPPED`: solid caution triangle.
- [x] Worn pump, `TRIPPED`: solid caution triangle.
- [x] Clear trip and restore health: normal water waves return.

### Unavailable

- [x] Healthy pump, `available=false`: solid X only.
- [x] Worn pump, `available=false`: solid X takes priority over triangle.
- [x] Restore availability while still worn: triangle appears.
- [x] Restore availability and health: normal water waves return.

### Isolation

- [x] P-201 packet changes only Device 1.
- [x] P-203 packet changes only Device 2.
- [x] P-204 packet changes only Device 3.
- [x] A wrong `pump` field is ignored by the board.
- [x] Tank level changes do not alter any pump hazard state.
- [x] HH/LL/interlock changes do not alter any pump hazard state.
- [x] Pipeline/treatment restriction changes do not alter any pump hazard state.

### Link and protocol

- [x] One-shot packet transitions to link-loss display after 1.5 seconds.
- [x] `--hold` replay keeps the pump state live.
- [x] Malformed, oversized, wrong-version, wrong-device, and wrong-pump packets are rejected.
- [x] All three dedicated environments compile and upload.

## Acceptance criteria

- [x] Each Arduino visibly represents exactly one pump.
- [x] Trip and wear use the caution triangle.
- [x] Unavailable uses only the solid X.
- [x] No tank condition can trigger either pump animation.
- [x] P-201, P-203, and P-204 can be tested independently with fixture packets.
- [ ] The live gateway produces the same results from the FastAPI WebSocket state.
