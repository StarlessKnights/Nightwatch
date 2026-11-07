/**
 * AVON AI - Edge Hardware Visualizer Firmware
 * PlatformIO project for Arduino UNO R4 WiFi
 * 
 * Drives the built-in 12x8 LED Matrix based on live telemetry streamed from
 * the Raspberry Pi 5 Gateway via USB Serial (115200 baud).
 */

#include <Arduino.h>
#include "Arduino_LED_Matrix.h"
#include <ArduinoJson.h>
#include "protocol.h"

// 12x8 LED Matrix driver
ArduinoLEDMatrix matrix;

// Serial reception buffer
constexpr size_t SERIAL_BUF_LEN = 256;
char rxBuffer[SERIAL_BUF_LEN];
size_t rxIndex = 0;

// Telemetry state instances
TankPumpTelemetry tankData = {600.0f, 1000.0f, 180.0f, 200.0f, PUMP_RUNNING, 1.0f, PUMP_STOPPED, 1.0f, ALARM_NONE, false};
PipelineTelemetry pipeData = {200.0f, 250.0f, 1.0f, 1, 0};
TreatmentTelemetry trtData = {200.0f, 400.0f, 1.0f, 0};

// Timing variables
unsigned long lastPacketTime = 0;
unsigned long lastAnimUpdate = 0;
unsigned long lastHeartbeat = 0;
uint8_t animFrame = 0;

// 12x8 Framebuffer (8 rows of 12 bits)
uint8_t frameBuffer[MATRIX_ROWS][MATRIX_COLS];

// Helper to push frameBuffer to the UNO R4 matrix
void renderFrameBuffer() {
    uint32_t rawFrame[3] = {0, 0, 0};
    
    // The UNO R4 matrix takes 3 x 32-bit integers representing the 96 LEDs
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

// Clear the frame buffer
void clearBuffer() {
    memset(frameBuffer, 0, sizeof(frameBuffer));
}

// -------------------------------------------------------------
// WATERFLOW ANIMATION ENGINE (Device 2 - Pipeline Hero Display)
// -------------------------------------------------------------
void updatePipelineAnimation() {
    clearBuffer();

    float flow = pipeData.flow_bbl_hr;
    
    if (flow <= 1.0f || pipeData.direction == 0) {
        // Zero flow / Tripped state: Draw stationary empty pipe boundary and centered 'X' or dashes
        for (int c = 0; c < MATRIX_COLS; c++) {
            frameBuffer[0][c] = 1; // Top pipe wall
            frameBuffer[7][c] = 1; // Bottom pipe wall
        }
        // Centered static dashes
        for (int c = 2; c < 10; c += 3) {
            frameBuffer[3][c] = 1;
            frameBuffer[4][c] = 1;
        }
        renderFrameBuffer();
        return;
    }

    // Dynamic wave / fluid particle animation
    // Pipe boundaries
    for (int c = 0; c < MATRIX_COLS; c++) {
        frameBuffer[0][c] = 1; // Top pipe wall
        frameBuffer[7][c] = 1; // Bottom pipe wall
    }

    // Directional flowing chevrons: >> >> >>
    for (int col = 0; col < MATRIX_COLS; col++) {
        int virtualCol = (col - animFrame + MATRIX_COLS * 4) % 4;
        
        if (pipeData.direction > 0) { // Forward flow
            if (virtualCol == 0) {
                frameBuffer[2][col] = 1;
                frameBuffer[3][col] = 1;
                frameBuffer[4][col] = 1;
                frameBuffer[5][col] = 1;
            } else if (virtualCol == 1) {
                frameBuffer[1][col] = 1;
                frameBuffer[6][col] = 1;
            }
        } else { // Backpressure / Reverse
            if (virtualCol == 2) {
                frameBuffer[2][col] = 1;
                frameBuffer[3][col] = 1;
                frameBuffer[4][col] = 1;
                frameBuffer[5][col] = 1;
            } else if (virtualCol == 1) {
                frameBuffer[1][col] = 1;
                frameBuffer[6][col] = 1;
            }
        }
    }

    // Restriction bottleneck indicator (if throttled)
    if (pipeData.restriction_factor < 0.95f) {
        frameBuffer[1][5] = 1;
        frameBuffer[2][5] = 1;
        frameBuffer[5][5] = 1;
        frameBuffer[6][5] = 1;
        frameBuffer[1][6] = 1;
        frameBuffer[2][6] = 1;
        frameBuffer[5][6] = 1;
        frameBuffer[6][6] = 1;
    }

    renderFrameBuffer();
}

// -------------------------------------------------------------
// TANK & PUMP STATION RENDERER (Device 1)
// -------------------------------------------------------------
void updateTankAnimation() {
    clearBuffer();

    // 1. Tank Level Bar Graph (Columns 0 to 3, Rows 0 to 7)
    // 0 bbl = row 7 empty; 1000 bbl = all rows 0..7 full
    int fillRows = map((int)constrain(tankData.level_bbl, 0, 1000), 0, 1000, 0, 8);
    for (int r = 0; r < fillRows; r++) {
        int targetRow = 7 - r;
        for (int c = 0; c < 4; c++) {
            frameBuffer[targetRow][c] = 1;
        }
    }

    // High alarm marker at row 1 (900 bbl), High-High marker at row 0 (950 bbl)
    if (tankData.level_bbl >= 900.0f) {
        // Flash top row if in alarm
        if ((animFrame % 2) == 0) {
            frameBuffer[0][0] = 0;
            frameBuffer[0][3] = 0;
        }
    }

    // 2. Pump Status Icons (Columns 6 to 11)
    // Duty Pump P-203 (Rows 1..3, Cols 6..9)
    if (tankData.p203_state == PUMP_RUNNING) {
        // Rotating vane or solid block
        frameBuffer[2][7] = 1;
        frameBuffer[2][8] = 1;
        if ((animFrame % 2) == 0) {
            frameBuffer[1][7] = 1;
            frameBuffer[3][8] = 1;
        } else {
            frameBuffer[3][7] = 1;
            frameBuffer[1][8] = 1;
        }
    } else if (tankData.p203_state == PUMP_TRIPPED) {
        // Draw 'X' for tripped
        frameBuffer[1][7] = 1; frameBuffer[1][9] = 1;
        frameBuffer[2][8] = 1;
        frameBuffer[3][7] = 1; frameBuffer[3][9] = 1;
    }

    // Standby Pump P-204 (Rows 5..7, Cols 6..9)
    if (tankData.p204_state == PUMP_RUNNING) {
        frameBuffer[6][7] = 1;
        frameBuffer[6][8] = 1;
        if ((animFrame % 2) == 0) {
            frameBuffer[5][7] = 1;
            frameBuffer[7][8] = 1;
        } else {
            frameBuffer[7][7] = 1;
            frameBuffer[5][8] = 1;
        }
    } else if (tankData.p204_state == PUMP_STARTING) {
        // Pulsing dot
        if ((animFrame % 2) == 0) {
            frameBuffer[6][8] = 1;
        }
    }

    renderFrameBuffer();
}

// -------------------------------------------------------------
// TREATMENT FACILITY RENDERER (Device 3)
// -------------------------------------------------------------
void updateTreatmentAnimation() {
    clearBuffer();

    // Intake swirling vortex
    int centerCol = 6;
    int centerRow = 4;
    
    int step = animFrame % 4;
    switch (step) {
        case 0:
            frameBuffer[centerRow - 1][centerCol] = 1;
            frameBuffer[centerRow][centerCol + 1] = 1;
            break;
        case 1:
            frameBuffer[centerRow][centerCol + 1] = 1;
            frameBuffer[centerRow + 1][centerCol] = 1;
            break;
        case 2:
            frameBuffer[centerRow + 1][centerCol] = 1;
            frameBuffer[centerRow][centerCol - 1] = 1;
            break;
        case 3:
            frameBuffer[centerRow][centerCol - 1] = 1;
            frameBuffer[centerRow - 1][centerCol] = 1;
            break;
    }
    
    // Outer boundary walls
    for (int r = 1; r < 7; r++) {
        frameBuffer[r][1] = 1;
        frameBuffer[r][10] = 1;
    }

    renderFrameBuffer();
}

// Calculate dynamic animation delay based on flow rate
unsigned long calculateFrameDelay() {
#if DEVICE_ID == 2
    float flow = pipeData.flow_bbl_hr;
    if (flow <= 1.0f) return 500;
    // Map 1..250 bbl/hr to 300ms .. 35ms
    long delayVal = 320 - (long)((flow / 250.0f) * 280.0f);
    return (unsigned long)constrain(delayVal, 35, 320);
#elif DEVICE_ID == 1
    // Tank update tick
    return 150;
#else
    // Treatment update tick
    return 120;
#endif
}

// Parse incoming JSON string
void processJsonPacket(const char* jsonStr) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, jsonStr);
    if (err) {
        return; // Malformed JSON ignored
    }

    int dev = doc["dev"] | 0;
    
    // Only process packets matching our DEVICE_ID (or broadcast dev=0)
    if (dev != 0 && dev != DEVICE_ID) {
        return;
    }

    lastPacketTime = millis();

#if DEVICE_ID == 1
    tankData.level_bbl = doc["lvl"] | tankData.level_bbl;
    tankData.capacity_bbl = doc["cap"] | tankData.capacity_bbl;
    tankData.inflow_rate = doc["inflow"] | tankData.inflow_rate;
    tankData.outflow_rate = doc["outflow"] | tankData.outflow_rate;
    tankData.p203_state = doc["p203"]["state"] | tankData.p203_state;
    tankData.p203_capacity_factor = doc["p203"]["cf"] | tankData.p203_capacity_factor;
    tankData.p204_state = doc["p204"]["state"] | tankData.p204_state;
    tankData.p204_capacity_factor = doc["p204"]["cf"] | tankData.p204_capacity_factor;
    tankData.alarm_level = doc["alarm"] | tankData.alarm_level;
    tankData.interlock_tripped = (doc["interlock"] | 0) != 0;

#elif DEVICE_ID == 2
    pipeData.flow_bbl_hr = doc["flow"] | pipeData.flow_bbl_hr;
    pipeData.capacity_bbl_hr = doc["cap"] | pipeData.capacity_bbl_hr;
    pipeData.restriction_factor = doc["restr"] | pipeData.restriction_factor;
    pipeData.direction = doc["dir"] | pipeData.direction;
    pipeData.alarm = doc["alarm"] | pipeData.alarm;

#elif DEVICE_ID == 3
    trtData.flow_bbl_hr = doc["flow"] | trtData.flow_bbl_hr;
    trtData.capacity_bbl_hr = doc["cap"] | trtData.capacity_bbl_hr;
    trtData.intake_factor = doc["intake_factor"] | trtData.intake_factor;
    trtData.alarm = doc["alarm"] | trtData.alarm;
#endif
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);

    matrix.begin();
    clearBuffer();
    renderFrameBuffer();

    lastPacketTime = millis();
}

void loop() {
    // 1. Non-blocking serial packet reading
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
            // Buffer overflow protection
            rxIndex = 0;
        }
    }

    // 2. Standalone Demo Mode (if no serial packet received in 6 seconds)
    if (millis() - lastPacketTime > 6000) {
        // Run self-test demo
        pipeData.flow_bbl_hr = 180.0f;
        pipeData.direction = 1;
        tankData.level_bbl = 750.0f;
    }

    // 3. Animation Refresh Step
    unsigned long interval = calculateFrameDelay();
    if (millis() - lastAnimUpdate >= interval) {
        lastAnimUpdate = millis();
        animFrame++;

#if DEVICE_ID == 1
        updateTankAnimation();
#elif DEVICE_ID == 2
        updatePipelineAnimation();
#elif DEVICE_ID == 3
        updateTreatmentAnimation();
#endif
    }

    // 4. Built-in LED heartbeat toggle
    if (millis() - lastHeartbeat >= 500) {
        lastHeartbeat = millis();
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }
}
