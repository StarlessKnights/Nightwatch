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
constexpr char FIRMWARE_VERSION[] = "0.2.0-pump";
