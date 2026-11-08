#pragma once
#include <Arduino.h>
#include "config.h"
#include "model.h"

struct PeripheralTelemetry {
  uint16_t knob = 1000;      // 0..1000 (thousandths, 1000 = 100% health/throttle)
  float temperature_c = 25.0f; // degrees Celsius
  uint16_t light = 500;       // 0..1023 ambient reading
  bool knobChanged = false;
  bool tempAlert = false;
};

class HalPeripherals {
 public:
  void begin();
  void update(unsigned long now, PumpState pumpState);
  void emitTelemetryIfDue(unsigned long now, uint8_t devId, const char *assignedPump, PumpState pumpState);
  const PeripheralTelemetry &getTelemetry() const { return telemetry; }

 private:
  PeripheralTelemetry telemetry;

  // Smoothing filters & timers
  float smoothedKnob = 1023.0f;
  float smoothedTempAdc = 300.0f;
  float simTemperature = 25.0f;
  float smoothedLight = 500.0f;

  unsigned long lastSampleMs = 0;
  unsigned long lastTxMs = 0;
  unsigned long lastBuzzerToggleMs = 0;
  bool buzzerState = false;
  PumpState lastPumpState = PUMP_STOPPED;

  void sampleSensors(PumpState pumpState);
  void updateBuzzer(unsigned long now, PumpState pumpState);
};
