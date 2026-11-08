#pragma once
#include <Arduino.h>

enum PumpState : uint8_t { PUMP_STOPPED, PUMP_RUNNING, PUMP_STARTING, PUMP_DEGRADED, PUMP_TRIPPED, PUMP_UNAVAILABLE };

struct DisplayState {
  uint32_t seq = 0;
  uint8_t dev = 0;
  PumpState pump = PUMP_STOPPED;
  uint16_t wear = 1000;
  uint16_t level = 0;
  uint16_t capacity = 1000;
  bool available = true;
  unsigned long lastPacketMs = 0;
  bool hasPacket = false;
};
