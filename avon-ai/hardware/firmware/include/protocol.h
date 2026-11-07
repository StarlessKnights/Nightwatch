#pragma once

#include <Arduino.h>

/**
 * AVON AI - Hardware Telemetry Protocol Structures
 * Supports 5 Arduino UNO R4 WiFi 12x8 LED Matrix nodes.
 */

#ifndef DEVICE_ID
#define DEVICE_ID 2
#endif

#ifndef DEVICE_ROLE
#define DEVICE_ROLE "PIPELINE_1"
#endif

// Pump state enum
enum PumpState {
    PUMP_STOPPED = 0,
    PUMP_RUNNING = 1,
    PUMP_TRIPPED = 2,
    PUMP_STARTING = 3
};

// Alarm severity enum
enum AlarmSeverity {
    ALARM_NONE = 0,
    ALARM_HIGH = 1,
    ALARM_CRITICAL_HH = 2
};

// Device 1: Tank T-104 & Dual Pumps (P-203 Duty, P-204 Standby)
struct Tank104Telemetry {
    float level_bbl;
    float capacity_bbl;
    float inflow_rate;
    float outflow_rate;
    uint8_t p203_state;
    float p203_cf;
    uint8_t p204_state;
    float p204_cf;
    uint8_t alarm_level;
    bool interlock_tripped;
};

// Device 2 & 5: Pipelines PL-1 & PL-2
struct PipelineTelemetry {
    float flow_bbl_hr;
    float capacity_bbl_hr;
    float restriction_factor;
    int8_t direction; // 1 = forward, 0 = stopped, -1 = reverse
    uint8_t alarm;
};

// Device 3: Treatment Facility TRT-1
struct TreatmentTelemetry {
    float flow_bbl_hr;
    float capacity_bbl_hr;
    float intake_factor;
    uint8_t alarm;
};

// Device 4: Tank T-101 & Pump P-201
struct Tank101Telemetry {
    float level_bbl;
    float capacity_bbl;
    float inflow_rate;
    float outflow_rate;
    uint8_t p201_state;
    float p201_cf;
    uint8_t alarm_level;
    bool interlock_tripped;
};

// Matrix dimensions for Arduino UNO R4
constexpr uint8_t MATRIX_COLS = 12;
constexpr uint8_t MATRIX_ROWS = 8;
