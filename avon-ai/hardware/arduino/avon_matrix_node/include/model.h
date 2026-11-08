#pragma once
#include <Arduino.h>

enum PumpState : uint8_t {
  PUMP_STOPPED = 0,
  PUMP_RUNNING = 1,
  PUMP_STARTING = 2,
  PUMP_DEGRADED = 3,
  PUMP_TRIPPED = 4,
  PUMP_UNAVAILABLE = 5
};

struct DisplayState {
  uint32_t seq = 0;
  uint8_t dev = 0;
  PumpState pump = PUMP_STOPPED;
  uint16_t wear = 1000;
  uint16_t level = 0;
  uint16_t capacity = 1000;
  float flow = 0.0f;
  float max_flow = 200.0f;
  bool alarm = false;
  bool airgap = false;
  bool available = true;
  unsigned long lastPacketMs = 0;
  bool hasPacket = false;
};
