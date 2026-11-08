#include "profiles.h"

static void cautionTriangle(Framebuffer &f) {
  f.set(6, 0);
  f.set(5, 1); f.set(7, 1);
  f.set(4, 2); f.set(8, 2);
  f.set(3, 3); f.set(9, 3);
  f.set(2, 4); f.set(10, 4);
  f.set(1, 5); f.set(11, 5);
  f.hline(0, 11, 6);
  f.set(6, 2); f.set(6, 3); f.set(6, 5);
}

static void solidX(Framebuffer &f) {
  for (int y = 0; y < 8; ++y) {
    f.set(2 + y, y);
    f.set(3 + y, y);
    f.set(9 - y, y);
    f.set(8 - y, y);
  }
}

static void padlockIcon(Framebuffer &f) {
  // Arch shackle (inverted U)
  f.hline(4, 7, 0);
  f.set(3, 1); f.set(4, 1); f.set(7, 1); f.set(8, 1);
  f.set(3, 2); f.set(8, 2);

  // Solid body (rows 3 to 7, cols 2 to 9)
  for (int y = 3; y <= 7; ++y) {
    f.hline(2, 9, y);
  }
  // Keyhole cutout (cols 5..6, rows 4..6)
  f.set(5, 4, false); f.set(6, 4, false);
  f.set(5, 5, false); f.set(6, 5, false);
  f.set(5, 6, false);
}

static void drawPumpRing(Framebuffer &f) {
  // Top & bottom caps
  f.hline(4, 7, 0);
  f.hline(4, 7, 7);
  // Corners
  f.set(2, 1); f.set(3, 1); f.set(8, 1); f.set(9, 1);
  f.set(2, 6); f.set(3, 6); f.set(8, 6); f.set(9, 6);
  // Sides
  f.vline(1, 2, 5);
  f.vline(10, 2, 5);
}

static void drawImpellerVanes(Framebuffer &f, int rotFrame) {
  // Center hub (2x2)
  f.set(5, 3); f.set(6, 3);
  f.set(5, 4); f.set(6, 4);

  switch (rotFrame & 3) {
    case 0:
      // Plus orientation ('+')
      f.vline(5, 1, 2); f.vline(6, 1, 2);
      f.vline(5, 5, 6); f.vline(6, 5, 6);
      f.hline(3, 4, 3); f.hline(3, 4, 4);
      f.hline(7, 8, 3); f.hline(7, 8, 4);
      break;

    case 1:
      // Clockwise tilt ~25 degrees
      f.set(7, 1); f.set(6, 2);
      f.set(8, 4); f.set(7, 5);
      f.set(4, 6); f.set(5, 5);
      f.set(3, 3); f.set(4, 2);
      break;

    case 2:
      // Diagonal orientation ('X')
      f.set(3, 1); f.set(4, 2);
      f.set(8, 1); f.set(7, 2);
      f.set(3, 6); f.set(4, 5);
      f.set(8, 6); f.set(7, 5);
      break;

    case 3:
      // Clockwise tilt ~65 degrees
      f.set(8, 2); f.set(7, 2);
      f.set(6, 6); f.set(6, 5);
      f.set(3, 5); f.set(4, 5);
      f.set(5, 1); f.set(5, 2);
      break;
  }
}

static void waterWaves(const DisplayState &s, Framebuffer &f, uint8_t phase) {
  uint16_t cap = (s.capacity > 0) ? s.capacity : 1000;
  float fraction = (float)s.level / (float)cap;
  fraction = constrain(fraction, 0.0f, 1.0f);
  int fillRows = (int)(fraction * 8.0f + 0.5f);
  if (fillRows <= 0) return;

  int surface = 8 - fillRows;
  for (int y = surface + 1; y < 8; ++y) {
    for (int x = 0; x < 12; ++x) {
      f.set(x, y, ((x + phase + y * 2) % 11) != 0);
    }
  }

  // Moving wave crest at liquid surface
  for (int x = 0; x < 12; ++x) {
    int crest = (x + phase) % 6;
    f.set(x, surface, crest != 0 && crest != 5);
  }

  // Occasional droplets above surface when space allows
  if (surface > 0) {
    int drop = (phase / 2) % 12;
    f.set(drop, surface - 1);
    if ((phase % 8) == 0) f.set((drop + 5) % 12, surface - 1);
  }
}

static void flowingOutput(const DisplayState &s, Framebuffer &f, unsigned long now) {
  float flowVal = (s.flow > 0.0f) ? s.flow : 100.0f;
  float maxF = (s.max_flow > 0.0f) ? s.max_flow : 200.0f;
  float throughput = constrain(flowVal / maxF, 0.1f, 3.0f);
  int offset = (int)(now * throughput / 50.0f);

  for (int y = 0; y < 8; ++y) {
    int dy = (y <= 3) ? (3 - y) : (y - 4);
    for (int x = 0; x < 12; ++x) {
      // Directional chevron ripple wavefront moving left-to-right
      int pos = (x - offset + dy) % 5;
      if (pos < 0) pos += 5;
      if (pos == 0 || pos == 1) {
        f.set(x, y, true);
      }
      // Core jet stream particles along center rows
      if ((y == 3 || y == 4) && ((x - offset * 2) % 3 == 0)) {
        f.set(x, y, true);
      }
    }
  }
}

static void renderTank(const DisplayState &s, Framebuffer &f, unsigned long now, uint8_t phase) {
  bool isAlarm = s.alarm || (s.level >= 950);
  if (isAlarm && (((now / 250) & 1) == 0)) {
    cautionTriangle(f);
    return;
  }
  waterWaves(s, f, phase);
}

static void renderPump(const DisplayState &s, Framebuffer &f, unsigned long now) {
  if (s.pump == PUMP_TRIPPED) {
    solidX(f);
    return;
  }
  if (s.pump == PUMP_STOPPED) {
    drawPumpRing(f);
    return;
  }
  if (s.wear < 500 && (((now / 400) & 1) == 0)) {
    cautionTriangle(f);
    return;
  }

  drawPumpRing(f);
  float flowVal = (s.flow > 0.0f) ? s.flow : 100.0f;
  float maxF = (s.max_flow > 0.0f) ? s.max_flow : 200.0f;
  float speedFactor = constrain(flowVal / maxF, 0.1f, 3.0f);
  int rotFrame = (int)(now * speedFactor / 60.0f) % 4;
  drawImpellerVanes(f, rotFrame);
}

static void renderOutput(const DisplayState &s, Framebuffer &f, unsigned long now, bool airgapKillswitch) {
  if (s.airgap || airgapKillswitch) {
    padlockIcon(f);
    return;
  }
  flowingOutput(s, f, now);
}

void renderProfile(const DisplayState &s, Framebuffer &f, unsigned long now, uint8_t phase, uint8_t deviceId, bool airgapKillswitch) {
  f.clear();
  if (deviceId == 1) {
    renderTank(s, f, now, phase);
  } else if (deviceId == 2) {
    renderPump(s, f, now);
  } else {
    renderOutput(s, f, now, airgapKillswitch);
  }
}
