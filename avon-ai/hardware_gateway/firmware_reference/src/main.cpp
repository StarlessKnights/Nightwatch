/**
 * AVON AI - 5-Node Edge Hardware Visualizer Firmware
 * PlatformIO project for Arduino UNO R4 WiFi
 * 
 * Drives the built-in 12x8 LED Matrix across 5 distinct plant assets:
 *   Device 1: Tank T-104 & Pumps P-203/P-204
 *   Device 2: Pipeline PL-1 (Upper Fluid Flow)
 *   Device 3: Treatment Facility TRT-1 (Intake Hub)
 *   Device 4: Tank T-101 & Pump P-201
 *   Device 5: Pipeline PL-2 (Lower Fluid Flow)
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

// Telemetry state instances for the 5 devices
Tank104Telemetry tank104Data = {600.0f, 1000.0f, 180.0f, 200.0f, PUMP_RUNNING, 1.0f, PUMP_STOPPED, 1.0f, ALARM_NONE, false};
PipelineTelemetry pipe1Data  = {200.0f, 250.0f, 1.0f, 1, 0};
TreatmentTelemetry trtData   = {200.0f, 400.0f, 1.0f, 0};
Tank101Telemetry tank101Data = {550.0f, 1000.0f, 200.0f, 200.0f, PUMP_RUNNING, 1.0f, ALARM_NONE, false};
PipelineTelemetry pipe2Data  = {200.0f, 250.0f, 1.0f, 1, 0};

// Timing variables
unsigned long lastPacketTime = 0;
unsigned long lastAnimUpdate = 0;
unsigned long lastHeartbeat = 0;
uint8_t animFrame = 0;

// 12x8 Framebuffer (8 rows x 12 cols)
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
// WATERFLOW PIPELINE RENDERER (Devices 2 & 5)
// -------------------------------------------------------------
void renderPipelineFlow(const PipelineTelemetry& pipe) {
    clearBuffer();

    float flow = pipe.flow_bbl_hr;
    
    // Top and bottom pipe boundaries
    for (int c = 0; c < MATRIX_COLS; c++) {
        frameBuffer[0][c] = 1;
        frameBuffer[7][c] = 1;
    }

    if (flow <= 1.0f || pipe.direction == 0) {
        // Zero flow / Tripped state: static centered dashes
        for (int c = 2; c < 10; c += 3) {
            frameBuffer[3][c] = 1;
            frameBuffer[4][c] = 1;
        }
        renderFrameBuffer();
        return;
    }

    // Directional cascading chevrons: >> >> >>
    for (int col = 0; col < MATRIX_COLS; col++) {
        int virtualCol = (col - animFrame + MATRIX_COLS * 4) % 4;
        
        if (pipe.direction > 0) { // Forward flow
            if (virtualCol == 0) {
                frameBuffer[2][col] = 1; frameBuffer[3][col] = 1;
                frameBuffer[4][col] = 1; frameBuffer[5][col] = 1;
            } else if (virtualCol == 1) {
                frameBuffer[1][col] = 1; frameBuffer[6][col] = 1;
            }
        } else { // Backpressure / reverse flow
            if (virtualCol == 2) {
                frameBuffer[2][col] = 1; frameBuffer[3][col] = 1;
                frameBuffer[4][col] = 1; frameBuffer[5][col] = 1;
            } else if (virtualCol == 1) {
                frameBuffer[1][col] = 1; frameBuffer[6][col] = 1;
            }
        }
    }

    // Restriction bottleneck indicator (if throttled)
    if (pipe.restriction_factor < 0.95f) {
        frameBuffer[1][5] = 1; frameBuffer[2][5] = 1; frameBuffer[5][5] = 1; frameBuffer[6][5] = 1;
        frameBuffer[1][6] = 1; frameBuffer[2][6] = 1; frameBuffer[5][6] = 1; frameBuffer[6][6] = 1;
    }

    renderFrameBuffer();
}

// -------------------------------------------------------------
// TANK T-104 & DUAL PUMPS RENDERER (Device 1)
// -------------------------------------------------------------
void renderTank104() {
    clearBuffer();

    // 1. Tank Fill Bar (Cols 0..3, Rows 0..7)
    int fillRows = map((int)constrain(tank104Data.level_bbl, 0, 1000), 0, 1000, 0, 8);
    for (int r = 0; r < fillRows; r++) {
        int targetRow = 7 - r;
        for (int c = 0; c < 4; c++) frameBuffer[targetRow][c] = 1;
    }

    // Alarm flash at HH limit
    if (tank104Data.level_bbl >= 900.0f && (animFrame % 2 == 0)) {
        frameBuffer[0][0] = 0; frameBuffer[0][3] = 0;
    }

    // 2. Duty Pump P-203 (Cols 6..9, Rows 1..3)
    if (tank104Data.p203_state == PUMP_RUNNING) {
        frameBuffer[2][7] = 1; frameBuffer[2][8] = 1;
        if (animFrame % 2 == 0) { frameBuffer[1][7] = 1; frameBuffer[3][8] = 1; }
        else                    { frameBuffer[3][7] = 1; frameBuffer[1][8] = 1; }
    } else if (tank104Data.p203_state == PUMP_TRIPPED) {
        frameBuffer[1][7] = 1; frameBuffer[1][9] = 1; frameBuffer[2][8] = 1;
        frameBuffer[3][7] = 1; frameBuffer[3][9] = 1; // 'X'
    }

    // 3. Standby Pump P-204 (Cols 6..9, Rows 5..7)
    if (tank104Data.p204_state == PUMP_RUNNING) {
        frameBuffer[6][7] = 1; frameBuffer[6][8] = 1;
        if (animFrame % 2 == 0) { frameBuffer[5][7] = 1; frameBuffer[7][8] = 1; }
        else                    { frameBuffer[7][7] = 1; frameBuffer[5][8] = 1; }
    } else if (tank104Data.p204_state == PUMP_STARTING) {
        if (animFrame % 2 == 0) frameBuffer[6][8] = 1; // Pulsing
    }

    renderFrameBuffer();
}

// -------------------------------------------------------------
// TANK T-101 & P-201 RENDERER (Device 4)
// -------------------------------------------------------------
void renderTank101() {
    clearBuffer();

    // 1. Tank Fill Bar (Cols 0..3, Rows 0..7)
    int fillRows = map((int)constrain(tank101Data.level_bbl, 0, 1000), 0, 1000, 0, 8);
    for (int r = 0; r < fillRows; r++) {
        int targetRow = 7 - r;
        for (int c = 0; c < 4; c++) frameBuffer[targetRow][c] = 1;
    }

    // 2. Pump P-201 (Cols 6..9, Rows 3..5)
    if (tank101Data.p201_state == PUMP_RUNNING) {
        frameBuffer[4][7] = 1; frameBuffer[4][8] = 1;
        if (animFrame % 2 == 0) { frameBuffer[3][7] = 1; frameBuffer[5][8] = 1; }
        else                    { frameBuffer[5][7] = 1; frameBuffer[3][8] = 1; }
    } else if (tank101Data.p201_state == PUMP_TRIPPED) {
        frameBuffer[3][7] = 1; frameBuffer[3][9] = 1; frameBuffer[4][8] = 1;
        frameBuffer[5][7] = 1; frameBuffer[5][9] = 1;
    }

    renderFrameBuffer();
}

// -------------------------------------------------------------
// TREATMENT FACILITY TRT-1 RENDERER (Device 3)
// -------------------------------------------------------------
void renderTreatment() {
    clearBuffer();

    // Swirling intake vortex
    int centerCol = 6;
    int centerRow = 4;
    int step = animFrame % 4;

    switch (step) {
        case 0: frameBuffer[centerRow - 1][centerCol] = 1; frameBuffer[centerRow][centerCol + 1] = 1; break;
        case 1: frameBuffer[centerRow][centerCol + 1] = 1; frameBuffer[centerRow + 1][centerCol] = 1; break;
        case 2: frameBuffer[centerRow + 1][centerCol] = 1; frameBuffer[centerRow][centerCol - 1] = 1; break;
        case 3: frameBuffer[centerRow][centerCol - 1] = 1; frameBuffer[centerRow - 1][centerCol] = 1; break;
    }

    // Outer boundary walls
    for (int r = 1; r < 7; r++) {
        frameBuffer[r][1] = 1;
        frameBuffer[r][10] = 1;
    }

    // Flashing constraint alert
    if (trtData.intake_factor < 0.95f && (animFrame % 2 == 0)) {
        frameBuffer[0][5] = 1; frameBuffer[0][6] = 1;
        frameBuffer[7][5] = 1; frameBuffer[7][6] = 1;
    }

    renderFrameBuffer();
}

// Dynamic frame delay calculation
unsigned long calculateFrameDelay() {
#if DEVICE_ID == 2
    float flow = pipe1Data.flow_bbl_hr;
    if (flow <= 1.0f) return 500;
    long delayVal = 320 - (long)((flow / 250.0f) * 280.0f);
    return (unsigned long)constrain(delayVal, 35, 320);
#elif DEVICE_ID == 5
    float flow = pipe2Data.flow_bbl_hr;
    if (flow <= 1.0f) return 500;
    long delayVal = 320 - (long)((flow / 250.0f) * 280.0f);
    return (unsigned long)constrain(delayVal, 35, 320);
#elif DEVICE_ID == 1 || DEVICE_ID == 4
    return 150;
#else
    return 120;
#endif
}

void processJsonPacket(const char* jsonStr) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, jsonStr);
    if (err) return;

    int dev = doc["dev"] | 0;
    if (dev != 0 && dev != DEVICE_ID) return;

    lastPacketTime = millis();

#if DEVICE_ID == 1
    tank104Data.level_bbl = doc["lvl"] | tank104Data.level_bbl;
    tank104Data.p203_state = doc["p203"]["state"] | tank104Data.p203_state;
    tank104Data.p203_cf = doc["p203"]["cf"] | tank104Data.p203_cf;
    tank104Data.p204_state = doc["p204"]["state"] | tank104Data.p204_state;
    tank104Data.p204_cf = doc["p204"]["cf"] | tank104Data.p204_cf;
    tank104Data.alarm_level = doc["alarm"] | tank104Data.alarm_level;
    tank104Data.interlock_tripped = (doc["interlock"] | 0) != 0;

#elif DEVICE_ID == 2
    pipe1Data.flow_bbl_hr = doc["flow"] | pipe1Data.flow_bbl_hr;
    pipe1Data.restriction_factor = doc["restr"] | pipe1Data.restriction_factor;
    pipe1Data.direction = doc["dir"] | pipe1Data.direction;
    pipe1Data.alarm = doc["alarm"] | pipe1Data.alarm;

#elif DEVICE_ID == 3
    trtData.flow_bbl_hr = doc["flow"] | trtData.flow_bbl_hr;
    trtData.intake_factor = doc["intake_factor"] | trtData.intake_factor;
    trtData.alarm = doc["alarm"] | trtData.alarm;

#elif DEVICE_ID == 4
    tank101Data.level_bbl = doc["lvl"] | tank101Data.level_bbl;
    tank101Data.p201_state = doc["p201"]["state"] | tank101Data.p201_state;
    tank101Data.p201_cf = doc["p201"]["cf"] | tank101Data.p201_cf;
    tank101Data.alarm_level = doc["alarm"] | tank101Data.alarm_level;
    tank101Data.interlock_tripped = (doc["interlock"] | 0) != 0;

#elif DEVICE_ID == 5
    pipe2Data.flow_bbl_hr = doc["flow"] | pipe2Data.flow_bbl_hr;
    pipe2Data.restriction_factor = doc["restr"] | pipe2Data.restriction_factor;
    pipe2Data.direction = doc["dir"] | pipe2Data.direction;
    pipe2Data.alarm = doc["alarm"] | pipe2Data.alarm;
#endif
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    matrix.begin();
    clearBuffer();
    renderFrameBuffer();
    lastPacketTime = millis();
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

    // Fallback demo if disconnected for > 6s
    if (millis() - lastPacketTime > 6000) {
        pipe1Data.flow_bbl_hr = 180.0f; pipe1Data.direction = 1;
        pipe2Data.flow_bbl_hr = 180.0f; pipe2Data.direction = 1;
        tank104Data.level_bbl = 750.0f;
        tank101Data.level_bbl = 650.0f;
    }

    // Frame refresh
    unsigned long interval = calculateFrameDelay();
    if (millis() - lastAnimUpdate >= interval) {
        lastAnimUpdate = millis();
        animFrame++;

#if DEVICE_ID == 1
        renderTank104();
#elif DEVICE_ID == 2
        renderPipelineFlow(pipe1Data);
#elif DEVICE_ID == 3
        renderTreatment();
#elif DEVICE_ID == 4
        renderTank101();
#elif DEVICE_ID == 5
        renderPipelineFlow(pipe2Data);
#endif
    }

    // Heartbeat
    if (millis() - lastHeartbeat >= 500) {
        lastHeartbeat = millis();
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }
}
