#pragma once

#include <Arduino.h>

/**
 * AVON AI - 5 Pump Network Protocol Definitions
 * All 5 Arduino UNO R4 WiFi boards act as active physical pump visualizers.
 */

#ifndef DEVICE_ID
#define DEVICE_ID 1
#endif

#ifndef PUMP_NAME
#define PUMP_NAME "P-203"
#endif

// Pump state codes matching Manas v1 protocol
enum PumpRunState {
    PUMP_STATE_STOPPED = 0,
    PUMP_STATE_RUNNING = 1,
    PUMP_STATE_STARTING = 2,
    PUMP_STATE_DEGRADED = 3,
    PUMP_STATE_TRIPPED = 4,
    PUMP_STATE_UNAVAILABLE = 5
};

// Limiting cause codes
enum LimitingCause {
    LIMIT_NONE = 0,
    LIMIT_PIPELINE = 1,
    LIMIT_TREATMENT = 2,
    LIMIT_TANK_VOLUME = 3
};

// Alarm severity codes
enum AlarmSeverity {
    ALARM_NONE = 0,
    ALARM_ADVISORY = 1,
    ALARM_HIGH = 2,
    ALARM_CRITICAL = 3
};

// Standardized telemetry packet for each pump node
struct PumpNodeTelemetry {
    uint8_t dev_id;
    uint16_t seq;
    uint8_t state;            // 0..5
    float flow_bbl_hr;       // Actual fluid throughput
    float rated_flow_bbl_hr; // Rated design capacity (e.g. 200)
    float capacity_factor;   // 0.0 .. 1.0 (degrade factor)
    uint8_t limiting_cause;  // 0=none, 1=pipeline, 2=treatment, 3=volume
    uint8_t alarm_level;     // 0=none, 1=advisory, 2=high, 3=critical
    bool interlock_shut_in;  // Inflow pump shut in by HH interlock
};

// Matrix dimensions
constexpr uint8_t MATRIX_COLS = 12;
constexpr uint8_t MATRIX_ROWS = 8;
