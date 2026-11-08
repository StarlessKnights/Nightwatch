#pragma once
#include <Arduino.h>

class Framebuffer {
 public:
  uint8_t pixels[8][12] = {};
  void clear();
  void set(int x, int y, bool on=true);
  void hline(int x0, int x1, int y, bool on=true);
  void vline(int x, int y0, int y1, bool on=true);
  void pack(uint32_t out[3]) const;
};
