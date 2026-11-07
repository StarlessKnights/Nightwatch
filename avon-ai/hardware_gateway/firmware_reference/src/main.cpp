/**
 * AVON AI - Physical Pump Node Firmware
 * PlatformIO project for Arduino UNO R4 WiFi
 * 
 * Drives the built-in 12x8 LED Matrix as an active industrial pump:
 *   - Suction Intake (Cols 0..2): Water particles flowing into the pump
 *   - Centrifugal Impeller (Cols 3..8): 
 *       * RUNNING: Rotating impeller vanes (fast spin)
 *       * DEGRADED: Slow, labored rotation (wear / cavitation)
 *       * STARTING: Pulsing center dot
 *       * TRIPPED: Stationary with flashing red 'X'
 *       * STOPPED: Idle / standby baseline
 *   - Discharge Pipe (Cols 9..11): Water particles surging out at speed proportional to flow_bbl_hr
 */

#include <Arduino.h>
#include "Arduino_LED_Matrix.h"
#include <ArduinoJson.h>
#include "protocol.h"

ArduinoLEDMatrix matrix;

// Serial reception buffer
constexpr size_t SERIAL_BUF_LEN = 256;
char rxBuffer[SERIAL_BUF_LEN];
size_t rxIndex = 0;

// Current pump telemetry state
PumpNodeTelemetry pump = {
    DEVICE_ID,
    0,
    PUMP_STATE_RUNNING, // default running for self-test
    200.0f,             // 200 bbl/hr
    200.0f,
    1.0f,
    LIMIT_NONE,
    ALARM_NONE,
    false
};

// Timing variables
unsigned long lastPacketTime = 0;
unsigned long lastAnimUpdate = 0;
unsigned long lastHeartbeat = 0;
uint8_t animFrame = 0;

// 12x8 Framebuffer
uint8_t frameBuffer[MATRIX_ROWS][MATRIX_COLS];

void renderFrameBuffer() {
    uint32_t rawFrame[3] = {0, 0, 0};
    for (int r = 0; r < MATRIX_ROWS; r++) {
        for (int c = 0; c < MATRIX_COLS; c++) {
            if (frameBuffer[r][c]) {
                int bitIndex = r * MATRIX_COLS + c;
                int wordIdx = bitIndex / 32;
                int bitOffset = 31 - (bitIndex % 32);
                rawFrame[wordIdx] |= (1UL << bitOffset);
            }
        }
    }
    matrix.loadFrame(rawFrame);
}

void clearBuffer() {
    memset(frameBuffer, 0, sizeof(frameBuffer));
}

// -------------------------------------------------------------
// PUMP MATRIX RENDERER
// -------------------------------------------------------------
void renderPump() {
    clearBuffer();

    bool is_flowing = (pump.state == PUMP_STATE_RUNNING || pump.state == PUMP_STATE_DEGRADED) && pump.flow_bbl_hr > 1.0f;

    // 1. Pipe boundaries (Top row 1 and Bottom row 6 on suction/discharge)
    frameBuffer[1][0] = 1; frameBuffer[1][1] = 1; frameBuffer[1][2] = 1; // Suction top
    frameBuffer[6][0] = 1; frameBuffer[6][1] = 1; frameBuffer[6][2] = 1; // Suction bottom
    frameBuffer[1][9] = 1; frameBuffer[1][10] = 1; frameBuffer[1][11] = 1; // Discharge top
    frameBuffer[6][9] = 1; frameBuffer[6][10] = 1; frameBuffer[6][11] = 1; // Discharge bottom

    // 2. Pump Casing / Volute (Cols 3..8, Rows 0..7)
    frameBuffer[0][5] = 1; frameBuffer[0][6] = 1; // Top casing
    frameBuffer[7][5] = 1; frameBuffer[7][6] = 1; // Bottom casing
    frameBuffer[1][4] = 1; frameBuffer[1][7] = 1;
    frameBuffer[6][4] = 1; frameBuffer[6][7] = 1;
    frameBuffer[2][3] = 1; frameBuffer[5][3] = 1;
    frameBuffer[2][8] = 1; frameBuffer[5][8] = 1;

    // 3. Suction Water Particles (Cols 0..2, Rows 3..4)
    if (is_flowing) {
        int suctionStep = animFrame % 3;
        frameBuffer[3][suctionStep] = 1;
        frameBuffer[4][suctionStep] = 1;
    }

    // 4. Central Impeller / Rotor Mechanism (Cols 4..7, Rows 2..5)
    if (pump.state == PUMP_STATE_RUNNING || pump.state == PUMP_STATE_DEGRADED) {
        // Rotating impeller vanes
        int rotStep = animFrame % 4;
        frameBuffer[3][5] = 1; frameBuffer[3][6] = 1; // Center hub
        frameBuffer[4][5] = 1; frameBuffer[4][6] = 1;

        if (rotStep == 0) {
            // Horizontal vane (+)
            frameBuffer[3][4] = 1; frameBuffer[4][4] = 1;
            frameBuffer[3][7] = 1; frameBuffer[4][7] = 1;
        } else if (rotStep == 1) {
            // Diagonal vane (\)
            frameBuffer[2][4] = 1; frameBuffer[5][7] = 1;
        } else if (rotStep == 2) {
            // Vertical vane (|)
            frameBuffer[2][5] = 1; frameBuffer[2][6] = 1;
            frameBuffer[5][5] = 1; frameBuffer[5][6] = 1;
        } else {
            // Diagonal vane (/)
            frameBuffer[2][7] = 1; frameBuffer[5][4] = 1;
        }
    } else if (pump.state == PUMP_STATE_TRIPPED) {
        // Pump TRIPPED: Draw large 'X' inside casing
        frameBuffer[2][4] = 1; frameBuffer[2][7] = 1;
        frameBuffer[3][5] = 1; frameBuffer[3][6] = 1;
        frameBuffer[4][5] = 1; frameBuffer[4][6] = 1;
        frameBuffer[5][4] = 1; frameBuffer[5][7] = 1;
    } else if (pump.state == PUMP_STATE_STARTING) {
        // Pump STARTING: Pulsing center dot
        if ((animFrame % 2) == 0) {
            frameBuffer[3][5] = 1; frameBuffer[3][6] = 1;
            frameBuffer[4][5] = 1; frameBuffer[4][6] = 1;
        }
    } else if (pump.state == PUMP_STATE_UNAVAILABLE) {
        // UNAVAILABLE / Lockout: Diagonal slash
        frameBuffer[2][4] = 1; frameBuffer[3][5] = 1;
        frameBuffer[4][6] = 1; frameBuffer[5][7] = 1;
    } else {
        // STOPPED / Standby idle: Stationary plus cross
        frameBuffer[3][5] = 1; frameBuffer[4][6] = 1;
    }

    // 5. Discharge Waterflow (Cols 9..11, Rows 3..4)
    if (is_flowing) {
        int dischargeStep = (animFrame % 3) + 9;
        frameBuffer[3][dischargeStep] = 1;
        frameBuffer[4][dischargeStep] = 1;
    }

    // 6. Alarm / Interlock Warning Flasher (Corners)
    if ((pump.alarm_level >= 2 || pump.interlock_shut_in) && (animFrame % 2 == 0)) {
        frameBuffer[0][0] = 1; frameBuffer[0][11] = 1;
        frameBuffer[7][0] = 1; frameBuffer[7][11] = 1;
    }

    renderFrameBuffer();
}

// Calculate animation speed based on flow rate and pump state
unsigned long calculateFrameDelay() {
    if (pump.state == PUMP_STATE_STOPPED || pump.state == PUMP_STATE_TRIPPED) {
        return 400; // Slow pulse for alarms
    }
    if (pump.state == PUMP_STATE_STARTING) {
        return 200; // Fast pulsing while starting
    }
    if (pump.state == PUMP_STATE_DEGRADED) {
        return 180; // Labored, slower rotation for degraded pump
    }

    // Running: dynamically scale delay from 160ms (low flow) to 45ms (max flow 200 bbl/hr)
    float flow = pump.flow_bbl_hr;
    if (flow <= 1.0f) return 300;
    long delayVal = 200 - (long)((flow / 250.0f) * 155.0f);
    return (unsigned long)constrain(delayVal, 40, 200);
}

void processJsonPacket(const char* jsonStr) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, jsonStr);
    if (err) return;

    int dev = doc["dev"] | doc["dev_id"] | 0;
    if (dev != 0 && dev != DEVICE_ID) return;

    lastPacketTime = millis();

    // Supports both compact Manas v1 format and verbose schema
    pump.seq = doc["seq"] | pump.seq;
    
    // State parsing
    if (doc.containsKey("state")) {
        pump.state = doc["state"];
    } else if (doc.containsKey("p1")) {
        pump.state = doc["p1"];
    }

    // Flow parsing
    if (doc.containsKey("flow")) {
        pump.flow_bbl_hr = doc["flow"];
    } else if (doc.containsKey("flow_bbl_hr")) {
        pump.flow_bbl_hr = doc["flow_bbl_hr"];
    }

    // Rated capacity
    if (doc.containsKey("max")) pump.rated_flow_bbl_hr = doc["max"];
    if (doc.containsKey("cap")) pump.rated_flow_bbl_hr = doc["cap"];

    // Capacity factor (Manas protocol sends rf/tf in thousandths e.g. 1000 = 1.0)
    if (doc.containsKey("cf")) {
        pump.capacity_factor = doc["cf"];
    } else if (doc.containsKey("rf")) {
        pump.capacity_factor = (float)(doc["rf"]) / 1000.0f;
    }

    // Limiting cause & alarms
    if (doc.containsKey("lim")) pump.limiting_cause = doc["lim"];
    if (doc.containsKey("al")) pump.alarm_level = doc["al"];
    if (doc.containsKey("il")) pump.interlock_shut_in = ((doc["il"] | 0) != 0);
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    matrix.begin();
    clearBuffer();
    renderFrameBuffer();
    lastPacketTime = millis();

    // Emit Manas hello greeting
    Serial.print("AVON|HELLO|v=1|dev=");
    Serial.print(DEVICE_ID);
    Serial.println("|profile=PUMP|fw=0.2.0");
}

void loop() {
    while (Serial.available() > 0) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (rxIndex > 0) {
                rxBuffer[rxIndex] = '\0';
                processJsonPacket(rxBuffer);
                rxIndex = 0;
            }
        } else if (rxIndex < (SERIAL_BUF_LEN - 1)) {
            rxBuffer[rxIndex++] = c;
        } else {
            rxIndex = 0;
        }
    }

    // Fallback demo if disconnected for > 5s
    if (millis() - lastPacketTime > 5000) {
        pump.state = PUMP_STATE_RUNNING;
        pump.flow_bbl_hr = 200.0f;
    }

    // Frame refresh
    unsigned long interval = calculateFrameDelay();
    if (millis() - lastAnimUpdate >= interval) {
        lastAnimUpdate = millis();
        animFrame++;
        renderPump();
    }

    // Heartbeat
    if (millis() - lastHeartbeat >= 500) {
        lastHeartbeat = millis();
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }
}
