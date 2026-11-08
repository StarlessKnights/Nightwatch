---
name: platformio-toolchain
description: >-
  Runbook for managing, compiling, and flashing PlatformIO multi-board environments,
  resolving missing pio CLI paths, and handling serial bootloaders on Windows and Linux.
  Activates when working with PlatformIO, platformio.ini, or flashing microcontrollers.
---

# PlatformIO Toolchain & Multi-Board Management Guide

This skill standardizes procedures for discovering, configuring, and compiling multi-target PlatformIO projects on Windows and Linux machines.

---

## 1. Locating the PlatformIO Binary

PlatformIO is frequently installed inside Python virtual environments (e.g. VS Code extension or global penv) that are not automatically added to the user's PowerShell or Bash `$PATH`.

### Windows Discovery & Alias
Check the default penv location before throwing `CommandNotFoundException`:
```powershell
# Default PlatformIO penv location on Windows
$pioPath = "$HOME\.platformio\penv\Scripts\pio.exe"

if (Test-Path $pioPath) {
    Set-Alias pio $pioPath
    Write-Host "Found PlatformIO at $pioPath"
} else {
    Write-Warning "PlatformIO penv not found. Install via: py -m pip install platformio"
}
```

### Linux / macOS Discovery
```bash
PIO_BIN="$HOME/.platformio/penv/bin/pio"
if [ -f "$PIO_BIN" ]; then
    alias pio="$PIO_BIN"
fi
```

---

## 2. Multi-Board `platformio.ini` Best Practices

### A. Provide Aliases for Environment Names
When collaborating across teams or merging branches, different developers may name environments differently (e.g., `uno_r4_pump1` vs `device_tank`). Define alias sections pointing to the same build flags to prevent script and documentation breakage:

```ini
[platformio]
default_envs = uno_r4_pump1, uno_r4_pump2, uno_r4_pump3
src_dir = src
include_dir = include

[env]
platform = renesas-ra
board = uno_r4_wifi
framework = arduino
monitor_speed = 115200
build_flags = -std=gnu++17
lib_deps = bblanchon/ArduinoJson@^7.0.0

; Node 1 Definition + Alias
[env:uno_r4_pump1]
build_flags = ${env.build_flags} -DDEVICE_ID=1

[env:device_tank]
build_flags = ${env.build_flags} -DDEVICE_ID=1

; Node 2 Definition + Alias
[env:uno_r4_pump2]
build_flags = ${env.build_flags} -DDEVICE_ID=2

[env:device_pipeline]
build_flags = ${env.build_flags} -DDEVICE_ID=2
```

---

## 3. Flashing Multi-Target Environments

### Sequential Uploading
When flashing multiple physical boards connected simultaneously:
1. Target specific upload ports explicitly:
   ```powershell
   pio run -e uno_r4_pump1 -t upload --upload-port COM4
   pio run -e uno_r4_pump2 -t upload --upload-port COM5
   pio run -e uno_r4_pump3 -t upload --upload-port COM6
   ```
2. If uploading without specifying `--upload-port`, plug in and flash **one board at a time** to guarantee that each firmware build lands on the intended physical unit.

### Serial Monitor Troubleshooting
If serial monitoring fails with `PermissionError` or access denied:
* Ensure Python gateway bridges or other serial terminal programs (PuTTY, Arduino IDE Serial Monitor) are closed before issuing `pio run -t upload`.
