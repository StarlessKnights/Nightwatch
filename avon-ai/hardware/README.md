# Arduino matrix nodes

Three Arduino UNO R4 WiFi boards render dedicated pump status on their built-in red 12x8 matrices. This is display-only telemetry; the boards do not control process equipment.

Assignments are fixed in firmware: Device 1 = P-201, Device 2 = P-203, Device 3 = P-204. The legacy PlatformIO environment names (`device_tank`, `device_pipeline`, and `device_treatment`) are retained for compatibility.

## PlatformIO

Install PlatformIO Core and build/flash each board environment from this directory:

```sh
pio run -e device_tank
pio run -e device_pipeline
pio run -e device_treatment
pio run -e device_tank -t upload --upload-port <PORT>
pio run -e device_pipeline -t upload --upload-port <PORT>
pio run -e device_treatment -t upload --upload-port <PORT>
pio device monitor -b 115200 --port <PORT>
```

The `corners` environment is a physical orientation check. It lights top-left, top-right, bottom-right, bottom-left in sequence. The default logical origin is top-left. Confirm this on all three boards after mounting.

For a single state to remain live during visual inspection, use the fixture sender's hold mode:

```sh
/Users/manast/.platformio/penv/bin/python tools/send_fixture.py <PORT> --device 1 --packet-index 0 --hold
```

Stop it with Ctrl-C. A one-shot packet intentionally falls back to the broken-link pattern after 1.5 seconds.

## USB identification and protocol

At boot each board prints `AVON|HELLO|...` with its compiled device ID. Gateway software should discover boards from this identity line, not by assuming USB port order. Protocol details and fixture packets are in `protocol/serial_protocol.md` and `protocol/examples.ndjson`.

## Board placement

Label each board and cable with its pump: P-201, P-203, and P-204. The LED matrices are monochrome, so state is encoded by shape, motion, and blinking. Provide printed asset labels for the audience.

Physical acceptance requires access to the boards and a live Person A gateway. Record actual results in `tests/hardware_acceptance.md`; software-only checks do not count as hardware acceptance.
