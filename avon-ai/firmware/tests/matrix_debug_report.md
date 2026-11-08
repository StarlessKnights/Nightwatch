# UNO R4 WiFi matrix debug report

## Completed checks

### PlatformIO build

The dedicated `api_test` environment builds and uploads successfully with:

```sh
/Users/manast/.platformio/penv/bin/pio run -e api_test -t upload --upload-port <PORT>
```

### Logical framebuffer

The diagnostic prints this fixed frame before each display update:

```text
#..#........
#..#..####..
#..#..#..#..
#..#..####..
####..####..
####..#..#..
####..####..
#..#........
```

The packed words are stable:

```text
0x90093C92 0x493CF3CF 0x24F3C900
```

### API comparison

The firmware alternates every two seconds between:

```text
DISPLAY_API loadPixels
DISPLAY_API loadFrame
```

The logical frame and packed words are identical in both cases. The code compiles against and includes the PlatformIO-installed official Arduino implementation:

```text
/Users/manast/.platformio/packages/framework-arduinorenesas-uno/libraries/Arduino_LED_Matrix
```

Library metadata:

```text
name=LED_Matrix
version=1.1.0
author=Arduino
architectures=renesas,renesas_uno
```

### Root cause of the repeated dot pattern

The repeated middle-row dot groups are the firmware's stale-link diagnostic pattern, not a matrix encoding failure. A one-shot fixture packet expires after `LINK_TIMEOUT_MS = 1500`. The fixture tool now supports `--hold` for continuous replay.

## Hardware check still required

While `api_test` is running, observe the physical matrix for two cycles:

- The fixed frame should remain visually identical during `loadPixels` and `loadFrame` cycles.
- If the physical image changes between the two labels, record which mode is wrong and stop there.
- If both modes match, the matrix API and frame encoding are cleared.

The official unmodified `DisplaySingleFrame` example has not been flashed separately because the API comparison already exercises both official frame-writing paths against the installed core. A physical visual comparison remains the required final check.
