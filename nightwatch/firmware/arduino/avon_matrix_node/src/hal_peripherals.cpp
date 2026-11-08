#include "hal_peripherals.h"

void HalPeripherals::begin() {
  // Initialize Modulino I2C communication on the UNO R4 WiFi Qwiic port (Wire1)
  Modulino.begin();

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

void HalPeripherals::sampleSensors(unsigned long now, PumpState pumpState, uint8_t devId) {
  // 1. Modulino Knob: Adjusts pump wear/throttle in real time
  if (hasModulinoKnob) {
    int pos = modulinoKnob.get();
    if (pos < 0) {
      pos = 0;
      modulinoKnob.set(0);
    } else if (pos > 100) {
      pos = 100;
      modulinoKnob.set(100);
    }

    if (pos != lastKnobPos) {
      lastKnobPos = pos;
      telemetry.knob = (uint16_t)(pos * 10); // scale 0..100 to 0..1000
      telemetry.knobChanged = true;

      uint8_t emitDev = (devId == 2) ? 2 : devId;
      float throttle = (float)telemetry.knob / 1000.0f;
      Serial.print("{\"dev\":");
      Serial.print(emitDev);
      Serial.print(",\"event\":\"KNOB\",\"knob\":");
      Serial.print(telemetry.knob);
      Serial.print(",\"throttle\":");
      Serial.print(throttle, 2);
      Serial.println("}");
    }
  }

  // 2. Modulino Buttons:
  // Button A: {"dev":3,"event":"AIRGAP_KILLSWITCH","state":true}
  // Button B: {"dev":3,"event":"PUMP_TRIP","target":"CHP-1"}
  // Button C: {"dev":3,"event":"TRIP_RESET","target":"CHP-1"}
  if (hasModulinoButtons) {
    if (modulinoButtons.update()) {
      bool btnA = (modulinoButtons.isPressed('A') == HIGH);
      bool btnB = (modulinoButtons.isPressed('B') == HIGH);
      bool btnC = (modulinoButtons.isPressed('C') == HIGH);

      uint8_t targetDev = (devId == 3) ? 3 : devId;

      if (btnA && !lastBtnA) {
        airgapKillswitch = true;
        Serial.print("{\"dev\":");
        Serial.print(targetDev);
        Serial.println(",\"event\":\"AIRGAP_KILLSWITCH\",\"state\":true}");
        if (hasModulinoBuzzer) modulinoBuzzer.tone(1500, 200);
        if (hasModulinoPixels) {
          for (int i = 0; i < 8; i++) modulinoPixels.set(i, RED, 50);
          modulinoPixels.show();
        }
      } else if (btnB && !lastBtnB) {
        Serial.print("{\"dev\":");
        Serial.print(targetDev);
        Serial.println(",\"event\":\"PUMP_TRIP\",\"target\":\"CHP-1\"}");
        if (hasModulinoBuzzer) modulinoBuzzer.tone(600, 100);
      } else if (btnC && !lastBtnC) {
        Serial.print("{\"dev\":");
        Serial.print(targetDev);
        Serial.println(",\"event\":\"TRIP_RESET\",\"target\":\"CHP-1\"}");
        if (hasModulinoBuzzer) modulinoBuzzer.tone(1000, 100);
      }

      lastBtnA = btnA;
      lastBtnB = btnB;
      lastBtnC = btnC;
    }
  }

  // 3. Modulino Thermo: Reads real temperature over I2C
  if (hasModulinoThermo) {
    float t_c = modulinoThermo.getTemperature();
    if (!isnan(t_c) && t_c > -40.0f && t_c < 125.0f) {
      telemetry.temperature_c = t_c;
    }
  } else {
    float targetTemp = 23.0f;
    if (pumpState == PUMP_RUNNING) {
      targetTemp = (telemetry.knob < 500) ? 76.0f : 44.0f;
    } else if (pumpState == PUMP_TRIPPED) {
      targetTemp = 60.0f;
    }
    simTemperature += (targetTemp - simTemperature) * 0.02f;
    telemetry.temperature_c = simTemperature;
  }

  // 4. Modulino Light: Ambient lux
  if (hasModulinoLight) {
    modulinoLight.update();
    int lux = modulinoLight.getLux();
    telemetry.light = (uint16_t)constrain(lux, 0, 1023);
  }

  // 5. Modulino Distance (ToF) if present
  if (hasModulinoDistance && modulinoDistance.available()) {
    telemetry.distance_mm = modulinoDistance.get();
  }
}

void HalPeripherals::updateBuzzerAndLeds(unsigned long now, PumpState pumpState) {
  if (hasModulinoPixels) {
    if (airgapKillswitch) {
      bool flash = ((now / 200) & 1) == 0;
      for (int i = 0; i < 8; i++) {
        if (flash) {
          modulinoPixels.set(i, RED, 40);
        } else {
          modulinoPixels.set(i, 0, 0, 0, 0);
        }
      }
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
    if (pumpState != lastPumpState) {
      if (pumpState == PUMP_STARTING) {
        modulinoBuzzer.tone(1800, 80);
      } else if (pumpState == PUMP_UNAVAILABLE) {
        modulinoBuzzer.tone(600, 100);
      }
      lastPumpState = pumpState;
    }

    if (pumpState == PUMP_TRIPPED) {
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

void HalPeripherals::update(unsigned long now, PumpState pumpState, uint8_t devId) {
  if ((uint32_t)(now - lastSampleMs) >= 50) { // 20 Hz sensor sampling
    lastSampleMs = now;
    sampleSensors(now, pumpState, devId);
  }
  updateBuzzerAndLeds(now, pumpState);
}

void HalPeripherals::emitTelemetryIfDue(unsigned long now, uint8_t devId, PumpState pumpState) {
  // Emit periodic heartbeat / sensor status every 1000ms
  if ((uint32_t)(now - lastTxMs) < 1000) return;
  lastTxMs = now;

  Serial.print("{\"v\":2,\"dev\":");
  Serial.print(devId);
  Serial.print(",\"online\":1");
  Serial.print(",\"state\":");
  Serial.print((int)pumpState);
  Serial.print(",\"temp\":");
  Serial.print(telemetry.temperature_c, 1);
  Serial.print(",\"light\":");
  Serial.print(telemetry.light);
  if (telemetry.distance_mm >= 0) {
    Serial.print(",\"dist\":");
    Serial.print(telemetry.distance_mm);
  }
  if (airgapKillswitch) {
    Serial.print(",\"airgap\":1");
  }
  Serial.println("}");
}
