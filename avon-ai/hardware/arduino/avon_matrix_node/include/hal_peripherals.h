#pragma once
#include <Arduino.h>
#include "config.h"
#include "model.h"

// Official Arduino Modulino Qwiic library
#include <Arduino_Modulino.h>

struct PeripheralTelemetry {
  uint8_t targetDev = 1;        // Currently targeted pump (1=P-201, 2=P-203, 3=P-204)
  uint16_t knob = 1000;         // 0..1000 (thousandths, 1000 = 100% health/throttle)
  float temperature_c = 25.0f;  // degrees Celsius
  uint16_t light = 500;         // ambient reading
  int16_t distance_mm = -1;     // Modulino Distance (-1 if not present)
  uint8_t tripDev = 0;          // 0 = none, 1=P-201, 2=P-203, 3=P-204
  bool knobChanged = false;
  bool buttonPressed = false;
  bool tempAlert = false;
  bool hasKnob = false;
  bool hasButtons = false;
};

class HalPeripherals {
 public:
  void begin();
  void update(unsigned long now, PumpState pumpState);
  void emitTelemetryIfDue(unsigned long now, uint8_t devId, const char *assignedPump, PumpState pumpState);

  const PeripheralTelemetry &getTelemetry() const { return telemetry; }
  bool hasKnob() const { return hasModulinoKnob; }
  uint8_t getTargetDev() const { return targetDev; }
  unsigned long getTargetSwitchedMs() const { return targetSwitchedMs; }

 private:
  PeripheralTelemetry telemetry;

  // Modulino Qwiic Modules
  ModulinoKnob modulinoKnob;
  ModulinoButtons modulinoButtons;
  ModulinoThermo modulinoThermo;
  ModulinoBuzzer modulinoBuzzer;
  ModulinoLight modulinoLight;
  ModulinoDistance modulinoDistance;
  ModulinoPixels modulinoPixels;

  // Hardware presence flags detected on the Qwiic bus
  bool hasModulinoKnob = false;
  bool hasModulinoButtons = false;
  bool hasModulinoThermo = false;
  bool hasModulinoBuzzer = false;
  bool hasModulinoLight = false;
  bool hasModulinoDistance = false;
  bool hasModulinoPixels = false;

  bool lastBtnA = false;
  bool lastBtnB = false;
  bool lastBtnC = false;

  // Channel switching for single Modulino Knob
  uint8_t targetDev = 1;                // 1=P-201, 2=P-203, 3=P-204
  int pumpKnobPos[4] = {100, 100, 100, 100}; // Stores wear pos per device (1..3)
  int lastKnobPos = 100;
  unsigned long targetSwitchedMs = 0;

  float simTemperature = 25.0f;
  unsigned long lastSampleMs = 0;
  unsigned long lastTxMs = 0;
  unsigned long lastBuzzerToggleMs = 0;
  bool buzzerActive = false;
  PumpState lastPumpState = PUMP_STOPPED;

  void sampleSensors(unsigned long now, PumpState pumpState);
  void updateBuzzerAndLeds(unsigned long now, PumpState pumpState);
};
