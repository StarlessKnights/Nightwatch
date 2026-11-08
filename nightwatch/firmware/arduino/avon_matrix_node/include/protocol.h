#pragma once
#include "model.h"

enum ParseResult : uint8_t { PARSE_IGNORED, PARSE_INVALID, PARSE_VALID };
ParseResult parsePacket(const char *line, uint8_t deviceId, DisplayState &state, unsigned long now);
