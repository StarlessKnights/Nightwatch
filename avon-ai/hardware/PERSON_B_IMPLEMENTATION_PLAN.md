# Person B implementation plan: three Arduino UNO R4 WiFi visual nodes

## 1. Goal and scope

Build one non-blocking firmware codebase that drives the built-in 12x8 LED matrix on three Arduino UNO R4 WiFi boards:

- Device 1: T-104 tank level plus P-203/P-204 pump state.
- Device 2: PL-1 flow, speed, direction, and restriction (the hero display).
- Device 3: TRT-1 intake and treatment backpressure.

Person B owns the Arduino firmware, matrix graphics, serial protocol implementation on the Arduino side, board identification, bench tests, and animation tuning. Person A owns the Raspberry Pi gateway and must translate the existing FastAPI WebSocket envelope into the serial messages defined below.

This plan assumes all three boards are **UNO R4 WiFi**, not UNO R4 Minima. Only the WiFi model has the built-in matrix. The matrix is 12x8 **red/monochrome**, so states must be distinguished by shape, position, blink rate, and motion rather than green/amber/red colors.

## 2. Repository layout to create

```text
hardware/
  README.md                         # Flashing, wiring, board placement, demo checklist
  protocol/
    serial_protocol.md              # Frozen Person A/Person B interface contract
    examples.ndjson                 # Valid, invalid, stale, and boundary packets
  arduino/
    avon_matrix_node/
      avon_matrix_node.ino          # setup(), loop(), profile selection
      config.h                      # DEVICE_ID, baud, orientation, timeouts
      protocol.h/.cpp               # line receiver, validation, state update
      model.h                       # enums and normalized display state
      framebuffer.h/.cpp            # safe 12x8 pixel primitives and packing
      scheduler.h/.cpp              # millis()-based animation timers
      profile_tank_pumps.h/.cpp      # Device 1 renderer
      profile_pipeline.h/.cpp        # Device 2 renderer
      profile_treatment.h/.cpp       # Device 3 renderer
      diagnostics.h/.cpp             # boot, link-lost, and bad-packet patterns
  tools/
    send_fixture.py                 # optional Person B bench sender
  tests/
    golden_frames.md                # expected 12x8 frames for review
    hardware_acceptance.md          # per-scene physical test sheet
```

Use a single sketch and shared renderer code. During the first implementation, set `DEVICE_ID` to 1, 2, or 3 in `config.h` before flashing and place a matching physical label on each board and USB cable. A later hardening step can store the ID in EEPROM or use three build environments, but that is not required for the first demo.

## 3. Freeze the serial contract before drawing animations

### Transport

- USB serial, 115200 baud, 8-N-1.
- One newline-terminated JSON object per message (NDJSON).
- Maximum input line: 192 bytes. Reject an overlong line and resynchronize at the next newline.
- Person A sends at 5-10 Hz and immediately after a state change.
- Each board accepts only messages whose `dev` equals its configured device ID.
- Integers are preferred on the wire. Factors are thousandths (`rf=1000` means 1.0) to avoid unnecessary floating-point parsing.
- Each valid message replaces the board's complete display state; no partial/delta packets.
- The board never commands the process. It may only return identity/diagnostic text to the gateway.

### Common fields

```json
{"v":1,"seq":120,"dev":1,"lvl":880,"cap":1000,"h":900,"hh":950,"p1":1,"p2":0,"al":2,"il":0}
{"v":1,"seq":121,"dev":2,"flow":90,"max":250,"rf":1000,"dir":1,"lim":0}
{"v":1,"seq":122,"dev":3,"flow":180,"max":400,"tf":500,"bp":1,"al":1}
```

Field meanings:

- `v`: protocol version; firmware initially supports only version 1.
- `seq`: monotonically increasing gateway sequence number; wraparound is allowed.
- `dev`: target device, 1-3.
- `al`: alarm severity: 0 none, 1 advisory/watch, 2 high, 3 HH/critical.
- Pump state codes (`p1`, `p2`): 0 stopped, 1 running, 2 starting, 3 degraded, 4 tripped, 5 unavailable.
- `il`: T-104 HH inflow interlock active, 0/1.
- `rf`: PL-1 restriction factor, 0-1000.
- `dir`: 1 forward, 0 stopped, -1 reverse/reserved.
- `lim`: PL-1 limiting cause: 0 none, 1 pipeline, 2 treatment, 3 tank volume.
- `tf`: TRT-1 intake factor, 0-1000.
- `bp`: treatment backpressure active, 0/1. Person A derives this from `TRT-1.intake_factor < 1` or any relevant pump whose `limited_by` is `treatment`.

### Mapping from the existing backend

Person A can populate the packets without backend changes from `state` in `/ws/sim`:

- Device 1: `state.tanks["T-104"]` and `state.pumps["P-203"]` / `["P-204"]`.
- Device 2: `state.pipelines["PL-1"]`; use the two pump `limited_by` fields for `lim`.
- Device 3: `state.treatment["TRT-1"]`; derive `bp` as described above.
- H and HH are currently 900 and 950 bbl in `data/config.json`; the gateway should send them rather than making them permanent firmware constants.

On boot, each Arduino writes one identity line:

```text
AVON|HELLO|v=1|dev=2|profile=pipeline|fw=0.1.0
```

This lets Person A bind logical devices by reported identity instead of assuming `/dev/ttyACM0`, `/dev/ttyACM1`, and `/dev/ttyACM2` remain in the same order.

### Failure behavior

- No valid packet yet: show a slow three-dot boot/search pattern.
- No valid packet for 1.5 seconds: show a recognizable broken-link pattern, alternating `-- --` with blank; do not continue presenting old telemetry as live.
- Malformed packet: ignore it, retain the last valid state until the stale timeout, and pulse the built-in `LED_BUILTIN` once.
- Unsupported protocol version or wrong device ID: ignore it.
- Sequence jump: accept the newest complete state. Sequence ordering is diagnostic, not safety logic.

## 4. Firmware architecture

The main loop must never call `delay()`. It should perform four small jobs on every pass:

1. Drain available serial bytes into a fixed-size line buffer.
2. On newline, validate and atomically commit a new `DisplayState`.
3. Ask the selected profile whether its next animation frame is due using `millis()`.
4. Render a 96-pixel framebuffer and send it with `ArduinoLEDMatrix::loadFrame()` (or `loadPixels()` after verifying orientation).

Keep the transport state separate from visual state. Parsing a message updates normalized values; renderers only read a stable snapshot. This prevents half-parsed packets from producing torn frames.

Recommended primitives:

- `clear()`, `setPixel(x,y)`, `hLine()`, `vLine()`, `blit3x3()`.
- `packFrame()` with one authoritative coordinate-to-bit mapping.
- `elapsed(now, then, interval)` using unsigned subtraction so `millis()` rollover is safe.
- Clamp every numeric input before rendering.
- Track `lastPacketMs`, `lastFrameMs`, `phase`, and `blinkPhase` independently.

First write a matrix orientation test that lights the four corners in a known sequence. Mark the physical left edge of each board after mounting. All later graphics must use logical coordinates where `(0,0)` is the top-left as seen by the judges.

## 5. Visual design by device

### Device 1: T-104 tank and pumps

Layout:

- Columns 0-3: tank outline/fill.
- Columns 4-7: P-203 duty pump icon.
- Columns 8-11: P-204 standby pump icon.

Tank rules:

- Map `lvl/cap` to 0-8 filled rows, filled bottom-up.
- Preserve a visible one-pixel outline or center bar so an empty tank is still recognizable.
- At `lvl >= h`, blink the top tank row at 2 Hz.
- At `lvl >= hh` or `al == 3`, alternate the entire tank region with an exclamation frame at 5 Hz.
- When `il == 1`, overlay a horizontal shut-in bar across the tank inlet/top.

Pump rules use motion rather than color:

- Running: four-phase rotating vane.
- Starting: expanding/pulsing center pixel.
- Degraded: rotating vane with every other expected frame omitted (visible stumble).
- Stopped: steady horizontal dash.
- Tripped: steady X with a periodic full-bright blink.
- Unavailable: boxed X, visually distinct from a trip.

The initial four-column-per-icon design is intentionally simple. Verify legibility on the physical board before adding labels or more detail.

### Device 2: PL-1 pipeline hero display

Use rows 2-5 as the pipe body and animate particles/chevrons across all 12 columns. Keep the top/bottom rows available for restriction and alarm accents.

Animation interval:

- `flow <= 0`: no forward animation; show two steady pipe rails with no particles.
- `flow > 0`: clamp to `max`, then map 1..`max` to approximately 400..40 ms per phase.
- Around 90 bbl/hr: deliberately slow, intermittent motion.
- Around 200 bbl/hr: smooth, obvious left-to-right motion.

Use 4-6 phases so the particles cross frame boundaries smoothly. Never derive motion from packet arrival frequency; the last telemetry value controls a local animation clock.

Restriction rules:

- If `rf < 950` or `lim == 1`, draw a two-column neck at columns 5-6 and flash it at 3 Hz.
- Continue particles through the neck at a density proportional to flow.
- If `lim == 2`, show the downstream/right barrier accent instead of a central restriction.
- If `lim == 3`, show a sparse inlet/left-side pattern.

### Device 3: TRT-1 intake and backpressure

Normal intake:

- Animate particles from the left into a 4x4 treatment vortex/drain on the right.
- Map `flow/max` to the same interval curve as Device 2 so the three boards look synchronized.

Constraint/backpressure:

- If `tf < 950` or `bp == 1`, replace the drain with a flashing vertical `||` barrier on columns 9-10.
- Reverse a small set of particles from right to left to communicate backup; this is a display metaphor, not a claim that backend flow is negative.
- At critical alarm, alternate the barrier with a full-width blocked frame.

## 6. Implementation sequence

### Milestone B0: hardware confirmation and visual calibration (half day)

- Confirm all three boards are UNO R4 WiFi and each built-in matrix works.
- Install/update the Arduino UNO R4 board package and compile the official matrix example.
- Run the four-corner orientation sketch on every board.
- Label boards/cables A/1, B/2, C/3 and photograph the intended mounting orientation.

Exit: all boards show the same logical orientation and accept sketches over their own USB cable.

### Milestone B1: protocol receiver and diagnostics (half to one day)

- Freeze `serial_protocol.md` with Person A.
- Implement the bounded newline receiver and complete-state validation.
- Emit the HELLO identity line.
- Add boot, malformed-packet, and stale-link indications.
- Test wrong IDs, truncated JSON, long lines, missing fields, and reconnects.

Exit: each board accepts only its own fixture packets and visibly reports a lost gateway.

### Milestone B2: framebuffer and scheduler (half day)

- Implement logical pixel primitives and one frame-packing function.
- Implement rollover-safe independent animation timers.
- Prove that sustained serial input does not stall animation and animation does not lose serial lines.

Exit: a 10-minute feeder run has no freezes, resets, or corrupted frames.

### Milestone B3: pipeline hero display first (one day)

- Build the forward particle animation.
- Tune 0, 90, 180, 200, and 250 bbl/hr fixtures.
- Add central restriction, downstream treatment limit, and stopped states.
- Film a short bench comparison of 90 versus 200 bbl/hr for design review.

Exit: an observer can correctly identify stopped, degraded, normal, and restricted states without being told which is which.

### Milestone B4: tank/pump and treatment profiles (one day)

- Build T-104 fill, H/HH, interlock, and both pump icons.
- Build treatment intake, constraint barrier, and reverse/backpressure effect.
- Tune blink rates to avoid visual noise when all three boards are active.

Exit: every state code and alarm level has a unique, documented visual.

### Milestone B5: three-board integration (half to one day)

- Connect all boards to the Pi gateway and verify HELLO-based mapping.
- Run the real WebSocket-to-serial bridge, not only fixtures.
- Rehearse the demo at the exact backend speed, board spacing, ambient light, and camera angle.
- Keep the backend at 1x for Scene 4 if the desired two-minute simulated standby delay should appear as about two real seconds.

Exit: complete the acceptance scenarios below three consecutive times without replugging or reflashing.

## 7. Acceptance scenarios

### Scene 1: normal operation

- Device 1 shows T-104 near 60%, P-203 running, P-204 stopped.
- Device 2 shows smooth forward flow near 200 bbl/hr.
- Device 3 shows steady intake with no barrier.

### Scene 2: P-203 degraded to 45%

- Device 1 shows P-203 degraded and T-104 rising from 880 bbl.
- Device 2 visibly slows to about 90 bbl/hr.
- Device 1 transitions through H and HH visuals at the configured thresholds.
- Starting/approving P-204 produces a starting pulse, then running vane and faster PL-1 animation.

### Scene 4: pump trip and auto-changeover

- P-203 changes to X when tripped.
- PL-1 stops immediately and remains visibly still during P-204's `STARTING` delay.
- P-204 pulses while starting, then rotates when running.
- PL-1 resumes without firmware reset or packet loss.
- At the second pump trip, both pump icons and the resulting no-flow/critical states are clear.

### Scene 5: treatment constraint

- Device 3 shows a flashing barrier and reverse/backpressure particles.
- Device 2 shows a downstream limitation rather than incorrectly claiming PL-1 itself is restricted.
- Device 1 continues to represent its real tank/pump state.

### Scene 6: interlock only

- Device 1 reaches HH indication and then shows the inflow interlock overlay.
- Displays continue to work even though the decision engine is disabled.

### Stretch: Scenes 3 and 7

- Scene 3: P-204 `unavailable` has a distinct boxed-X state.
- Scene 7: use `al` to show the sensor/alarm condition; do not pretend the matrix can explain transmitter disagreement in detail.

## 8. Bench test matrix

At minimum, save and replay fixtures for these boundaries:

- Level: 0, 50, 100, 899, 900, 949, 950, 1000, and out-of-range values.
- Flow: 0, 1, 90, 180, 200, 250, and above max.
- Pump: every code for both P-203 and P-204.
- Factors: 0, 500, 949, 950, 1000.
- Link: clean stream, fragmented writes, two packets in one USB write, malformed JSON, overlong line, disconnect, reconnect, and Arduino reset.
- Time: 10-minute soak plus a targeted scheduler rollover test using injected timestamps.

Record pass/fail and the firmware commit in `hardware/tests/hardware_acceptance.md`.

## 9. Coordination points with Person A

Person B should request these integration deliverables early:

- A gateway fixture mode that cycles normal -> degraded -> trip -> starting -> recovered -> treatment constraint without the full backend.
- HELLO-based serial-port discovery and reconnect after USB reset.
- A fixed 5-10 Hz outbound rate, even if WebSocket ticks arrive faster or slower.
- Complete packets with explicit defaults; never omit a field because its value did not change.
- A packet log option with timestamp, device, sequence, and raw line.

The interface-lock review is complete only when both people can replay `protocol/examples.ndjson` independently: Person A into a pseudo-terminal and Person B into each physical Arduino.

## 10. Demo hardening and fallback

- Use short, labeled USB cables and a powered USB hub sized for three boards.
- Disable laptop/Pi USB autosuspend for these ports during the demo.
- Mount boards in the same orientation and add a printed caption beneath each matrix; 12x8 graphics alone should not carry every semantic.
- Keep the last known firmware binaries/sketches and a one-command flash checklist.
- Maintain a local fixture/demo mode on the gateway. If the backend connection fails, it may drive a clearly labeled rehearsal pattern, but it must not be presented as live AVON telemetry.
- Do not add direct Wi-Fi/MQTT firmware until the USB version passes all scenarios. USB serial is simpler, deterministic, and matches the planned Pi gateway.

## 11. Definition of done

Person B's work is done when:

- One maintained firmware codebase builds for all three profiles.
- All three boards identify themselves and recover after gateway or USB restart.
- Serial parsing and rendering are fully non-blocking.
- The physical displays pass Scenes 1, 2, 4, 5, and 6 three times in a row.
- A judge can distinguish normal flow, degraded flow, stopped flow, pump trip, standby start, HH/interlock, pipeline restriction, and treatment backpressure from the displays plus their printed labels.
- The protocol, flash steps, fixture packets, and acceptance results are committed under `hardware/`.

