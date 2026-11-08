#pragma once

#ifndef DEVICE_ID
#define DEVICE_ID 1
#endif

#ifndef CORNER_TEST
#define CORNER_TEST 0
#endif

#ifndef MINIMAL_TEST
#define MINIMAL_TEST 0
#endif

#ifndef API_TEST
#define API_TEST 0
#endif

#if DEVICE_ID < 1 || DEVICE_ID > 3
#error DEVICE_ID must be 1, 2, or 3
#endif

#if DEVICE_ID == 1
constexpr char ASSIGNED_PUMP[] = "P-201";
#elif DEVICE_ID == 2
constexpr char ASSIGNED_PUMP[] = "P-203";
#else
constexpr char ASSIGNED_PUMP[] = "P-204";
#endif

constexpr unsigned long SERIAL_BAUD = 115200;
constexpr unsigned long LINK_TIMEOUT_MS = 1500;
constexpr unsigned long FRAME_INTERVAL_MS = 40;
constexpr size_t INPUT_LINE_MAX = 192;
constexpr char FIRMWARE_VERSION[] = "0.3.0-hil";

// ============================================================================
// Modular Peripheral Pin Assignments & Feature Toggles
// ============================================================================
// Any peripheral can be swapped, attached, or omitted without crashing.
#ifndef PIN_KNOB
#define PIN_KNOB A0         // Analog In: Manual throttle / wear potentiometer
#endif

#ifndef PIN_THERMAL
#define PIN_THERMAL A1      // Analog In: Pump casing temperature probe (TMP36 / NTC)
#endif

#ifndef PIN_LIGHT
#define PIN_LIGHT A2        // Analog In: Ambient photoresistor / light sensor
#endif

#ifndef PIN_BUZZER
#define PIN_BUZZER 8        // Digital / PWM Out: Piezo buzzer alarm
#endif

// Feature enable flags (1 = active, 0 = disabled)
#ifndef FEATURE_KNOB
#define FEATURE_KNOB 1
#endif

#ifndef FEATURE_THERMAL
#define FEATURE_THERMAL 1
#endif

#ifndef FEATURE_LIGHT
#define FEATURE_LIGHT 1
#endif

#ifndef FEATURE_BUZZER
#define FEATURE_BUZZER 1
#endif
