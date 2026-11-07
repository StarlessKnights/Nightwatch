#pragma once

#include <Arduino.h>

/**
 * AVON AI - Hardware Telemetry Protocol Structures
 * Matches PROTOCOL.md for Arduino UNO R4 12x8 LED Matrix nodes.
 */

#ifndef DEVICE_ID
#define DEVICE_ID 2
#endif

#ifndef DEVICE_ROLE
#define DEVICE_ROLE "PIPELINE"
#endif

// Pump state enum
enum PumpState {
    PUMP_STOPPED = 0,
    PUMP_RUNNING = 1,
    PUMP_TRIPPED = 2,
    PUMP_STARTING = 3
};

// Alarm priority enum
enum AlarmSeverity {
    ALARM_NONE = 0,
    ALARM_HIGH = 1,
    ALARM_CRITICAL_HH = 2
};

// Device 1: Tank T-104 & Pumps telemetry
struct TankPumpTelemetry {
    float level_bbl;
    float capacity_bbl;
    float inflow_rate;
    float outflow_rate;
    
    // Duty Pump (P-203)
    uint8_t p203_state;
    float p203_capacity_factor;
    
    // Standby Pump (P-204)
    uint8_t p204_state;
    float p204_capacity_factor;
    
    uint8_t alarm_level;
    bool interlock_tripped;
};

// Device 2: Pipeline PL-1 telemetry
struct PipelineTelemetry {
    float flow_bbl_hr;
    float capacity_bbl_hr;
    float restriction_factor;
    int8_t direction; // 1 = forward, 0 = stopped, -1 = reverse
    uint8_t alarm;
};

// Device 3: Treatment TRT-1 telemetry
struct TreatmentTelemetry {
    float flow_bbl_hr;
    float capacity_bbl_hr;
    float intake_factor;
    uint8_t alarm;
};

// Matrix dimensions for Arduino UNO R4
constexpr uint8_t MATRIX_COLS = 12;
constexpr uint8_t MATRIX_ROWS = 8;
