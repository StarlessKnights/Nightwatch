# Prompt: diagnose UNO R4 WiFi LED matrix frame encoding

You are debugging an Arduino UNO R4 WiFi LED matrix display. Research the current official Arduino documentation and official Arduino source code before proposing a fix. Use primary sources only:

- Arduino UNO R4 WiFi LED matrix tutorial and hardware documentation.
- The official `ArduinoCore-renesas` implementation of `Arduino_LED_Matrix`.
- Official Arduino examples in that repository.

Do not rely on forum guesses or third-party matrix libraries unless you clearly label them as secondary evidence.

## Hardware

- Board: Arduino UNO R4 WiFi, not UNO R4 Minima.
- Built-in display: 12 columns × 8 rows, monochrome red LEDs.
- PlatformIO board: `uno_r4_wifi`.
- Framework: Arduino Renesas core.
- Library discovered by PlatformIO: `LED_Matrix @ 1.1.0`.

## Repository

Project root:

```text
/Users/manast/AvonAI-SecondPass/avon-ai/hardware
```

PlatformIO configuration:

```ini
[platformio]
default_envs = device_tank, device_pipeline, device_treatment
src_dir = arduino/avon_matrix_node/src
include_dir = arduino/avon_matrix_node/include

[env]
platform = renesas-ra
board = uno_r4_wifi
framework = arduino
monitor_speed = 115200
build_flags = -std=gnu++17
lib_deps = bblanchon/ArduinoJson@^7.0.0
```

Relevant implementation files:

- `arduino/avon_matrix_node/src/main.cpp`
- `arduino/avon_matrix_node/src/framebuffer.cpp`
- `arduino/avon_matrix_node/src/framebuffer.h`
- `arduino/avon_matrix_node/src/profiles.cpp`

## Current rendering code

`Framebuffer` stores logical pixels as `pixels[8][12]`, with `pixels[y][x]` equal to 0 or 1. It has this output helper:

```cpp
void Framebuffer::pack(uint32_t out[3]) const {
  out[0]=out[1]=out[2]=0;
  for(int y=0;y<8;y++) {
    for(int x=0;x<12;x++) {
      if(pixels[y][x]) {
        const int i=y*12+x;
        out[i/32] |= (uint32_t)1 << (31-(i%32));
      }
    }
  }
}
```

The main loop currently sends frames using the official class like this:

```cpp
matrix.loadPixels(&fb.pixels[0][0],96);
```

The prior version used:

```cpp
uint32_t packed[3];
fb.pack(packed);
matrix.loadFrame(packed);
```

Both versions compiled and uploaded successfully.

## Corner test result

The PlatformIO `corners` environment lights one pixel at a time using:

```cpp
int xs[]={0,11,11,0};
int ys[]={0,0,7,7};
fb.set(xs[corner],ys[corner]);
```

The physical result appears correct: top-left, top-right, bottom-right, bottom-left. Therefore the board, USB upload, basic matrix initialization, and corner coordinate orientation appear to work.

## Actual symptom

After uploading `device_tank` and sending this valid packet:

```json
{"v":1,"seq":1,"dev":1,"lvl":600,"cap":1000,"h":900,"hh":950,"p1":1,"p2":0,"al":0,"il":0}
```

The display does **not** show the expected tank outline, fill, or pump icon. Instead it shows a single horizontal line in the middle row consisting of three groups of three red dots separated by one off LED, blinking on and off.

The tank renderer is intended to draw:

- Columns 0 and 3: tank side rails.
- Column range 1-2: liquid fill, bottom-up.
- Columns 4-7: P-203 icon.
- Columns 8-11: P-204 icon.
- An animated liquid ripple/bubble in the tank.
- A rotating vane for P-203.

## What you must investigate

1. Verify the exact API and expected memory layout for `ArduinoLEDMatrix::loadPixels()` in the current official Renesas core.
2. Verify the exact API and expected 3-word layout for `ArduinoLEDMatrix::loadFrame()`.
3. Determine whether `loadPixels()` expects:
   - row-major or column-major data;
   - 8×12 or 12×8 ordering;
   - bytes containing 0/1 values or packed bits;
   - a particular bit reversal or orientation transform.
4. Compare the official `MatrixIntro` and other official UNO R4 matrix examples with this project’s frame-writing code.
5. Explain why a logical tank/pump frame could collapse into a repeated horizontal middle-row pattern while the four-corner test still appears correct.
6. Identify whether the `LED_Matrix @ 1.1.0` library discovered by PlatformIO is the correct built-in matrix library or a conflicting library that changes the class/API.
7. Check whether `Arduino_LED_Matrix.h` should be included before or after another header, and whether `ArduinoGraphics` is relevant.
8. Check whether `matrix.begin()` must be called before `matrix.clear()` or `loadPixels()` in a different order.
9. Check whether `loadPixels()` is safe to call repeatedly every 40 ms, or whether `matrix.loadFrame()`/`renderFrame()` must be used for live animation.

## Required response

Return:

1. Links to the exact official Arduino documentation/source lines supporting the diagnosis.
2. The corrected frame representation and coordinate mapping.
3. A minimal known-good 12×8 test sketch that displays a filled rectangle and a distinct pump icon.
4. A minimal patch for this repository, naming the exact files and lines to change.
5. A verification procedure using PlatformIO:

```sh
/Users/manast/.platformio/penv/bin/pio run -e corners
/Users/manast/.platformio/penv/bin/pio run -e device_tank -t upload --upload-port <PORT>
/Users/manast/.platformio/penv/bin/python tools/send_fixture.py <PORT> --device 1 --packet-index 0
```

6. A short explanation of what should be visible on the physical matrix after the fix.

Do not declare success merely because PlatformIO compiles. The fix must explain and eliminate the observed middle-row three-groups-of-three pattern.
