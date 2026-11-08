#pragma once
#include <Arduino.h>
#include "config.h"
#include "model.h"

// Official Arduino Modulino Qwiic library
#include <Arduino_Modulino.h>

struct PeripheralTelemetry {
  uint16_t knob = 1000;         // 0..1000 (thousandths, 1000 = 100% health/throttle)
  float temperature_c = 25.0f;    // degrees Celsius
  uint16_t light = 500;          // ambient reading
  int16_t distance_mm = -1;      // Modulino Distance (-1 if not present)
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

  // Modulino Qwiic Modules
  ModulinoKnob modulinoKnob;
  ModulinoThermo modulinoThermo;
  ModulinoBuzzer modulinoBuzzer;
  ModulinoLight modulinoLight;
  ModulinoDistance modulinoDistance;
  ModulinoPixels modulinoPixels;

  // Hardware presence flags detected on the Qwiic bus
  bool hasModulinoKnob = false;
  bool hasModulinoThermo = false;
  bool hasModulinoBuzzer = false;
  bool hasModulinoLight = false;
  bool hasModulinoDistance = false;
  bool hasModulinoPixels = false;

  int lastKnobPos = 100;
  float simTemperature = 25.0f;

  unsigned long lastSampleMs = 0;
  unsigned long lastTxMs = 0;
  unsigned long lastBuzzerToggleMs = 0;
  bool buzzerActive = false;
  PumpState lastPumpState = PUMP_STOPPED;

  void sampleSensors(PumpState pumpState);
  void updateBuzzerAndLeds(unsigned long now, PumpState pumpState);
};
