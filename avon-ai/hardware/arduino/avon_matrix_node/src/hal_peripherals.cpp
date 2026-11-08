#include "hal_peripherals.h"

static const char* pumpNameForDev(uint8_t d) {
  if (d == 1) return "P-201";
  if (d == 2) return "P-203";
  return "P-204";
}

void HalPeripherals::begin() {
  // Initialize Modulino I2C communication on the UNO R4 WiFi Qwiic port (Wire1)
  Modulino.begin();

  // Start with target pump defaulting to this board's assigned ID
  targetDev = DEVICE_ID;
  telemetry.targetDev = targetDev;

  // Non-blocking auto-probe for each daisy-chained Modulino module
  hasModulinoKnob = modulinoKnob.begin();
  if (hasModulinoKnob) {
    telemetry.hasKnob = true;
    modulinoKnob.set(100);
    lastKnobPos = 100;
    telemetry.knob = 1000;
  }

  hasModulinoButtons = modulinoButtons.begin();
  if (hasModulinoButtons) {
    telemetry.hasButtons = true;
  }

  hasModulinoThermo = modulinoThermo.begin();
  hasModulinoBuzzer = modulinoBuzzer.begin();
  hasModulinoLight = modulinoLight.begin();
  hasModulinoDistance = modulinoDistance.begin();
  hasModulinoPixels = modulinoPixels.begin();

  if (hasModulinoPixels) {
    // Initial startup sweep on Modulino Pixels (Green = Ready)
    for (int i = 0; i < 8; i++) {
      modulinoPixels.set(i, GREEN, 20);
    }
    modulinoPixels.show();
  }
}

void HalPeripherals::sampleSensors(unsigned long now, PumpState pumpState) {
  // 1. Modulino Knob: Push-to-cycle target pump, rotate to set wear/health
  if (hasModulinoKnob) {
    // Detect click / push-down on rotary encoder knob
    if (modulinoKnob.isPressed()) {
      // Cycle target pump channel: 1 (P-201) -> 2 (P-203) -> 3 (P-204) -> 1 ...
      targetDev = (targetDev % 3) + 1;
      targetSwitchedMs = now;
      telemetry.targetDev = targetDev;

      // Restore and synchronize this target pump's last saved wear setting
      int saved = pumpKnobPos[targetDev];
      modulinoKnob.set(saved);
      lastKnobPos = saved;
      telemetry.knob = (uint16_t)(saved * 10);
      telemetry.knobChanged = true;

      // Audible feedback for channel switch: higher pitch for higher pump ID
      if (hasModulinoBuzzer) {
        modulinoBuzzer.tone(1000 + (targetDev * 400), 80);
      }

      // Visual feedback on Modulino Pixels
      if (hasModulinoPixels) {
        for (int i = 0; i < 8; i++) modulinoPixels.set(i, 0, 0, 0, 0);
        if (targetDev == 1) { modulinoPixels.set(0, BLUE, 40); modulinoPixels.set(1, BLUE, 40); }
        else if (targetDev == 2) { modulinoPixels.set(3, BLUE, 40); modulinoPixels.set(4, BLUE, 40); }
        else if (targetDev == 3) { modulinoPixels.set(6, BLUE, 40); modulinoPixels.set(7, BLUE, 40); }
        modulinoPixels.show();
      }
    }

    int pos = modulinoKnob.get();
    // Constrain position between 0 and 100
    if (pos < 0) {
      pos = 0;
      modulinoKnob.set(0);
    } else if (pos > 100) {
      pos = 100;
      modulinoKnob.set(100);
    }

    if (pos != lastKnobPos) {
      lastKnobPos = pos;
      pumpKnobPos[targetDev] = pos;
      telemetry.knob = (uint16_t)(pos * 10); // scale 0..100 to 0..1000
      telemetry.knobChanged = true;
    }
  }

  // 1b. Modulino Buttons: Button A -> Trip P-201, Button B -> Trip P-203, Button C -> Trip P-204
  if (hasModulinoButtons) {
    if (modulinoButtons.update()) {
      bool btnA = (modulinoButtons.isPressed('A') == HIGH);
      bool btnB = (modulinoButtons.isPressed('B') == HIGH);
      bool btnC = (modulinoButtons.isPressed('C') == HIGH);

      if (btnA && !lastBtnA) {
        telemetry.tripDev = 1;
        telemetry.buttonPressed = true;
        if (hasModulinoBuzzer) modulinoBuzzer.tone(500, 100);
      } else if (btnB && !lastBtnB) {
        telemetry.tripDev = 2;
        telemetry.buttonPressed = true;
        if (hasModulinoBuzzer) modulinoBuzzer.tone(500, 100);
      } else if (btnC && !lastBtnC) {
        telemetry.tripDev = 3;
        telemetry.buttonPressed = true;
        if (hasModulinoBuzzer) modulinoBuzzer.tone(500, 100);
      }

      lastBtnA = btnA;
      lastBtnB = btnB;
      lastBtnC = btnC;
    }
  }

  // 2. Modulino Thermo: Reads real temperature over I2C
  if (hasModulinoThermo) {
    float t_c = modulinoThermo.getTemperature();
    if (!isnan(t_c) && t_c > -40.0f && t_c < 125.0f) {
      telemetry.temperature_c = t_c;
    }
  } else {
    // Dynamic simulated thermal curve when no physical Thermo is plugged into Qwiic
    float targetTemp = 23.0f;
    if (pumpState == PUMP_RUNNING) {
      targetTemp = (telemetry.knob < 500) ? 76.0f : 44.0f;
    } else if (pumpState == PUMP_TRIPPED) {
      targetTemp = 60.0f;
    }
    simTemperature += (targetTemp - simTemperature) * 0.02f;
    telemetry.temperature_c = simTemperature;
  }

  // 3. Modulino Light: Ambient lux
  if (hasModulinoLight) {
    modulinoLight.update();
    int lux = modulinoLight.getLux();
    telemetry.light = (uint16_t)constrain(lux, 0, 1023);
  }

  // 4. Modulino Distance (ToF) if present
  if (hasModulinoDistance && modulinoDistance.available()) {
    telemetry.distance_mm = modulinoDistance.get();
  }
}

void HalPeripherals::updateBuzzerAndLeds(unsigned long now, PumpState pumpState) {
  // Update Modulino Pixels indicator if attached
  if (hasModulinoPixels) {
    // If channel was recently switched, hold channel indicator for 1.2s
    if (hasModulinoKnob && (uint32_t)(now - targetSwitchedMs) < 1200) {
      // Pixels show channel: 1, 2, or 3
      for (int i = 0; i < 8; i++) modulinoPixels.set(i, 0, 0, 0, 0);
      if (targetDev == 1) { modulinoPixels.set(0, CYAN, 40); modulinoPixels.set(1, CYAN, 40); }
      else if (targetDev == 2) { modulinoPixels.set(3, CYAN, 40); modulinoPixels.set(4, CYAN, 40); }
      else if (targetDev == 3) { modulinoPixels.set(6, CYAN, 40); modulinoPixels.set(7, CYAN, 40); }
      modulinoPixels.show();
    } else if (pumpState != lastPumpState) {
      ModulinoColor col = GREEN;
      int b = 25;
      if (pumpState == PUMP_STOPPED) { col = WHITE; b = 10; }
      else if (pumpState == PUMP_RUNNING) { col = (telemetry.knob < 500) ? YELLOW : GREEN; }
      else if (pumpState == PUMP_STARTING) { col = BLUE; }
      else if (pumpState == PUMP_DEGRADED) { col = YELLOW; }
      else if (pumpState == PUMP_TRIPPED) { col = RED; b = 50; }
      else if (pumpState == PUMP_UNAVAILABLE) { col = RED; b = 10; }

      for (int i = 0; i < 8; i++) {
        modulinoPixels.set(i, col, b);
      }
      modulinoPixels.show();
    }
  }

  // Modulino Buzzer tones
  if (hasModulinoBuzzer) {
    // State transitions
    if (pumpState != lastPumpState) {
      if (pumpState == PUMP_STARTING) {
        modulinoBuzzer.tone(1800, 80); // 80ms start chime
      } else if (pumpState == PUMP_UNAVAILABLE) {
        modulinoBuzzer.tone(600, 100); // 100ms low tone
      }
      lastPumpState = pumpState;
    }

    // Active alarms
    if (pumpState == PUMP_TRIPPED) {
      // Pulsing high-priority audible alarm: 150ms ON / 150ms OFF
      if ((uint32_t)(now - lastBuzzerToggleMs) >= 150) {
        lastBuzzerToggleMs = now;
        buzzerActive = !buzzerActive;
        if (buzzerActive) {
          modulinoBuzzer.tone(2400, 150);
        } else {
          modulinoBuzzer.tone(0, 150);
        }
      }
    } else if (pumpState == PUMP_DEGRADED) {
      // Intermittent chirp: 40ms beep once every 3.5 seconds
      if ((uint32_t)(now - lastBuzzerToggleMs) >= 3500) {
        lastBuzzerToggleMs = now;
        modulinoBuzzer.tone(1200, 40);
      }
    } else {
      if (buzzerActive) {
        modulinoBuzzer.tone(0, 50);
        buzzerActive = false;
      }
    }
  } else {
    lastPumpState = pumpState;
  }
}

void HalPeripherals::update(unsigned long now, PumpState pumpState) {
  if ((uint32_t)(now - lastSampleMs) >= 50) { // 20 Hz sensor sampling
    lastSampleMs = now;
    sampleSensors(now, pumpState);
  }
  updateBuzzerAndLeds(now, pumpState);
}

void HalPeripherals::emitTelemetryIfDue(unsigned long now, uint8_t devId, const char *assignedPump, PumpState pumpState) {
  // Emit on significant knob/sensor delta, button press, OR every 500ms heartbeat (2 Hz)
  bool due = telemetry.knobChanged || telemetry.buttonPressed || ((uint32_t)(now - lastTxMs) >= 500);
  if (!due) return;

  lastTxMs = now;
  telemetry.knobChanged = false;
  telemetry.buttonPressed = false;

  Serial.print("{\"v\":1,\"dev\":");
  Serial.print(devId);
  Serial.print(",\"pump\":\"");
  Serial.print(assignedPump);
  Serial.print("\",\"online\":1");

  if (hasModulinoKnob) {
    Serial.print(",\"target_dev\":");
    Serial.print(targetDev);
    Serial.print(",\"target_pump\":\"");
    Serial.print(pumpNameForDev(targetDev));
    Serial.print("\",\"knob\":");
    Serial.print(telemetry.knob);
  }

  if (telemetry.tripDev > 0) {
    Serial.print(",\"trip_dev\":");
    Serial.print(telemetry.tripDev);
    Serial.print(",\"trip_pump\":\"");
    Serial.print(pumpNameForDev(telemetry.tripDev));
    Serial.print("\"");
    telemetry.tripDev = 0;
  }

  Serial.print(",\"temp\":");
  Serial.print(telemetry.temperature_c, 1);
  Serial.print(",\"light\":");
  Serial.print(telemetry.light);
  if (telemetry.distance_mm >= 0) {
    Serial.print(",\"dist\":");
    Serial.print(telemetry.distance_mm);
  }
  Serial.print(",\"qwiic\":1");
  Serial.print(",\"state\":");
  Serial.print((int)pumpState);
  Serial.println("}");
}
