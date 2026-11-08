#include "hal_peripherals.h"

void HalPeripherals::begin() {
#if FEATURE_BUZZER
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
#endif

#if FEATURE_KNOB
  pinMode(PIN_KNOB, INPUT);
#endif

#if FEATURE_THERMAL
  pinMode(PIN_THERMAL, INPUT);
#endif

#if FEATURE_LIGHT
  pinMode(PIN_LIGHT, INPUT);
#endif
}

void HalPeripherals::sampleSensors(PumpState pumpState) {
#if FEATURE_KNOB
  int rawKnob = analogRead(PIN_KNOB);
  smoothedKnob = smoothedKnob * 0.85f + (float)rawKnob * 0.15f;
  uint16_t norm = (uint16_t)constrain((smoothedKnob * 1000.0f) / 1023.0f, 0.0f, 1000.0f);
  int delta = abs((int)norm - (int)telemetry.knob);
  if (delta >= 15) {  // 1.5% deadband to prevent serial spam from minor ADC noise
    telemetry.knob = norm;
    telemetry.knobChanged = true;
  }
#endif

#if FEATURE_THERMAL
  int rawTemp = analogRead(PIN_THERMAL);
  // If pin has a valid sensor reading (TMP36 or thermistor output in valid range)
  if (rawTemp >= 80 && rawTemp <= 950) {
    float voltage = ((float)rawTemp * 5.0f) / 1023.0f;
    float t_c = (voltage - 0.5f) * 100.0f; // TMP36 formula
    telemetry.temperature_c = constrain(t_c, 0.0f, 120.0f);
  } else {
    // Dynamic simulated pump thermal curve when no physical probe is wired
    float targetTemp = 23.0f;
    if (pumpState == PUMP_RUNNING) {
      targetTemp = (telemetry.knob < 500) ? 76.0f : 44.0f;
    } else if (pumpState == PUMP_TRIPPED) {
      targetTemp = 60.0f;
    }
    simTemperature += (targetTemp - simTemperature) * 0.02f;
    telemetry.temperature_c = simTemperature;
  }
#endif

#if FEATURE_LIGHT
  int rawLight = analogRead(PIN_LIGHT);
  smoothedLight = smoothedLight * 0.85f + (float)rawLight * 0.15f;
  telemetry.light = (uint16_t)constrain(smoothedLight, 0.0f, 1023.0f);
#endif
}

void HalPeripherals::updateBuzzer(unsigned long now, PumpState pumpState) {
#if FEATURE_BUZZER
  // State transition detection
  if (pumpState != lastPumpState) {
    if (pumpState == PUMP_STARTING) {
      tone(PIN_BUZZER, 1800, 80); // 80ms start chime
    } else if (pumpState == PUMP_UNAVAILABLE) {
      tone(PIN_BUZZER, 600, 100); // 100ms low tone
    }
    lastPumpState = pumpState;
  }

  // Active alarms
  if (pumpState == PUMP_TRIPPED) {
    // Pulsing high-priority audible alarm: 150ms ON / 150ms OFF
    if ((uint32_t)(now - lastBuzzerToggleMs) >= 150) {
      lastBuzzerToggleMs = now;
      buzzerState = !buzzerState;
      if (buzzerState) {
        tone(PIN_BUZZER, 2400);
      } else {
        noTone(PIN_BUZZER);
      }
    }
  } else if (pumpState == PUMP_DEGRADED) {
    // Intermittent advisory chirp: 40ms beep once every 3.5 seconds
    if ((uint32_t)(now - lastBuzzerToggleMs) >= 3500) {
      lastBuzzerToggleMs = now;
      tone(PIN_BUZZER, 1200, 40);
    }
  } else {
    if (buzzerState) {
      noTone(PIN_BUZZER);
      buzzerState = false;
    }
  }
#endif
}

void HalPeripherals::update(unsigned long now, PumpState pumpState) {
  if ((uint32_t)(now - lastSampleMs) >= 50) { // 20 Hz sensor sampling
    lastSampleMs = now;
    sampleSensors(pumpState);
  }
  updateBuzzer(now, pumpState);
}

void HalPeripherals::emitTelemetryIfDue(unsigned long now, uint8_t devId, const char *assignedPump, PumpState pumpState) {
  // Emit on significant knob/sensor delta OR every 500ms heartbeat (2 Hz)
  bool due = telemetry.knobChanged || ((uint32_t)(now - lastTxMs) >= 500);
  if (!due) return;

  lastTxMs = now;
  telemetry.knobChanged = false;

  Serial.print("{\"v\":1,\"dev\":");
  Serial.print(devId);
  Serial.print(",\"pump\":\"");
  Serial.print(assignedPump);
  Serial.print("\",\"online\":1,\"knob\":");
  Serial.print(telemetry.knob);
  Serial.print(",\"temp\":");
  Serial.print(telemetry.temperature_c, 1);
  Serial.print(",\"light\":");
  Serial.print(telemetry.light);
  Serial.print(",\"state\":");
  Serial.print((int)pumpState);
  Serial.println("}");
}
