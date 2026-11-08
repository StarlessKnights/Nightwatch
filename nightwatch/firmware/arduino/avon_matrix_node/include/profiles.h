#pragma once
#include "model.h"
#include "framebuffer.h"

void renderProfile(const DisplayState &s, Framebuffer &fb, unsigned long now, uint8_t phase, uint8_t deviceId = 1, bool airgapKillswitch = false);
