#pragma once
#include <Arduino.h>
#include "config.h"
#include "model.h"

// Official Arduino Modulino Qwiic library
#include <Arduino_Modulino.h>

struct PeripheralTelemetry {
  uint16_t knob = 1000;         // 0..1000 (thousandths, 1000 = 100% health/throttle)
  float temperature_c = 25.0f;  // degrees Celsius
  uint16_t light = 500;         // ambient reading
  int16_t distance_mm = -1;     // Modulino Distance (-1 if not present)
  bool knobChanged = false;
  bool buttonPressed = false;
  bool tempAlert = false;
  bool hasKnob = false;
  bool hasButtons = false;
};

class HalPeripherals {
 public:
  void begin();
  void update(unsigned long now, PumpState pumpState, uint8_t devId = DEVICE_ID);
  void emitTelemetryIfDue(unsigned long now, uint8_t devId, PumpState pumpState);

  const PeripheralTelemetry &getTelemetry() const { return telemetry; }
  bool hasKnob() const { return hasModulinoKnob; }
  bool isAirgapActive() const { return airgapKillswitch; }
  void setAirgapActive(bool active) { airgapKillswitch = active; }

 private:
  PeripheralTelemetry telemetry;
  bool airgapKillswitch = false;

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

  int lastKnobPos = 100;

  float simTemperature = 25.0f;
  unsigned long lastSampleMs = 0;
  unsigned long lastTxMs = 0;
  unsigned long lastBuzzerToggleMs = 0;
  bool buzzerActive = false;
  PumpState lastPumpState = PUMP_STOPPED;

  void sampleSensors(unsigned long now, PumpState pumpState, uint8_t devId);
  void updateBuzzerAndLeds(unsigned long now, PumpState pumpState);
};
