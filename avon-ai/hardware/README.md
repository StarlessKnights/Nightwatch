# Arduino matrix nodes

Three Arduino UNO R4 WiFi boards render AVON simulation state on their built-in red 12x8 matrices. This is display-only telemetry; the boards do not control process equipment.

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

## USB identification and protocol

At boot each board prints `AVON|HELLO|...` with its compiled device ID. Gateway software should discover boards from this identity line, not by assuming USB port order. Protocol details and fixture packets are in `protocol/serial_protocol.md` and `protocol/examples.ndjson`.

## Board placement

Place device 1 (T-104 / pumps), device 2 (PL-1), and device 3 (TRT-1) left to right. Label each board and cable. The LED matrices are monochrome, so state is encoded by shape, motion, and blinking. Provide printed asset labels for the audience.

Physical acceptance requires access to the boards and a live Person A gateway. Record actual results in `tests/hardware_acceptance.md`; software-only checks do not count as hardware acceptance.
