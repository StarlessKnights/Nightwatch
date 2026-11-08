# Pump-only hardware and end-to-end test plan

This replaces the earlier tank/pipeline/treatment checklist. Each UNO R4 is now a dedicated pump annunciator:

| Device | PlatformIO environment | Pump |
|---:|---|---|
| 1 | `device_tank` | P-201 |
| 2 | `device_pipeline` | P-203 |
| 3 | `device_treatment` | P-204 |

The legacy environment names are retained only for compatibility. No test should expect a pipeline renderer, treatment renderer, tank alarm renderer, or multiple pump icons.

## Test order

Run each section in order. For physical sections, wait for visual confirmation before moving to the next state.

### 1. Build and firmware identity

Run the complete build:

```sh
pio run
```

Expected environments: `device_tank`, `device_pipeline`, `device_treatment`, `corners`, `minimal`, and `api_test`.

Flash the environment matching the board under test. On serial startup, confirm:

```text
AVON|HELLO|v=1|dev=1|profile=pump|fw=0.2.0-pump
```

The `dev` value must match the physical assignment above.

### 2. Normal water-level animation

For each board, replay its first fixture packet with `--hold`.

- P-201: `--device 1 --packet-index 0`
- P-203: `--device 2 --packet-index 0`
- P-204: `--device 3 --packet-index 0`

Confirm that the full matrix shows animated water waves filled from the bottom to `lvl/cap`, with a moving surface crest and droplets. Pump lifecycle values do not replace the waves.

### 3. Level coverage

Use normal packets with different `lvl` values. The fixture set should cover approximately 20%, 60%, 88%, and 95%; if a value is not present in the fixture for a board, send an equivalent JSON packet manually.

Expected: approximately 2, 5, 7, and 8 rows of liquid respectively, with the wave surface tracking the top of the fill. No tank HH/LL logic is involved.

### 4. Hazard states

For every board, test these assigned-pump packets:

1. `w=500`, available: normal water waves (threshold is strict `<500`).
2. `w=499`, available: alternate between water waves and caution triangle.
3. `state=4`, available: solid caution triangle with no alternation.
4. `state=5`, unavailable: solid X with no triangle.

The unavailable X must take priority even if `w<500` or `state=4` is also present.

### 5. Stale-link behavior

Send one valid packet without `--hold`. Confirm the correct wave or hazard frame appears immediately, then the link-loss diagnostic appears after roughly 1.5 seconds. Restart the same assigned-pump packet with `--hold` and confirm recovery.

### 6. Protocol rejection and isolation

While a valid assigned-pump packet is held, send each of the following:

- wrong `dev`
- wrong `pump` name
- unsupported `v`
- missing `lvl`, `cap`, `w`, or `available`
- malformed JSON
- payload longer than 192 characters
- two newline-delimited packets in one serial write

Expected: invalid/wrong-target packets do not change the last valid frame. Parser errors pulse the onboard LED. The last valid state remains until stale timeout. A packet for P-201 must not affect Device 2 or Device 3.

### 7. Matrix API and orientation diagnostics

Flash `api_test` and confirm the alternating `loadPixels()` / `loadFrame()` frame remains identical. Flash `corners` on each physical board and confirm top-left, top-right, bottom-right, and bottom-left order. Reflash the correct pump environment after diagnostics.

### 8. Three-board integration

With all three boards connected, verify each HELLO identity and confirm the gateway routes by `dev`/pump identity rather than USB port order. Send simultaneous normal, wear, trip, and unavailable packets and confirm only the addressed pump board changes.

### 9. Live backend scenarios

These require Person A's gateway and FastAPI backend to emit the new common packet:

- P-201 normal level, wear, trip, unavailable, and recovery.
- P-203 normal level, wear, trip, unavailable, and recovery.
- P-204 normal level, wear, trip, unavailable, and recovery.
- Associated tank level changes update waves without changing hazard state.
- Backend tank HH/LL, pipeline restriction, treatment backpressure, sensor alarms, and engine-disabled flags do not independently trigger a pump triangle or X.

Run the complete live demo three times without reflashing or unplugging. Record any failures in `hardware_acceptance.md`.

## Commit gate

Do not commit until all physical checks above are confirmed, the complete build is green, all three assignments are verified, and the gateway is either validated or explicitly recorded as the remaining external dependency.
