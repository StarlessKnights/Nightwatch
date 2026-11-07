#pragma once
#include <Arduino.h>

enum PumpState : uint8_t { PUMP_STOPPED, PUMP_RUNNING, PUMP_STARTING, PUMP_DEGRADED, PUMP_TRIPPED, PUMP_UNAVAILABLE };
enum LimitCause : uint8_t { LIMIT_NONE, LIMIT_PIPELINE, LIMIT_TREATMENT, LIMIT_VOLUME };

struct DisplayState {
  uint32_t seq = 0;
  uint8_t dev = 0;
  uint16_t level = 0, capacity = 1000, high = 900, highHigh = 950;
  uint16_t flow = 0, maxFlow = 250;
  uint16_t restriction = 1000, treatmentFactor = 1000;
  PumpState pump1 = PUMP_STOPPED, pump2 = PUMP_STOPPED;
  LimitCause limit = LIMIT_NONE;
  int8_t direction = 0;
  uint8_t alarm = 0;
  bool interlock = false, backpressure = false;
  unsigned long lastPacketMs = 0;
  bool hasPacket = false;
};
