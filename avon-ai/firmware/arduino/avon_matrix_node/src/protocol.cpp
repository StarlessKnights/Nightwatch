#include "protocol.h"
#include "config.h"
#include <ArduinoJson.h>

ParseResult parsePacket(const char *line, uint8_t deviceId, DisplayState &state, unsigned long now) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err || !doc.is<JsonObject>()) {
    return PARSE_INVALID;
  }
  JsonObjectConst o = doc.as<JsonObjectConst>();

  if (!o["v"].is<int>() || !o["dev"].is<int>()) {
    return PARSE_INVALID;
  }

  int v = o["v"].as<int>();
  if (v != 1 && v != 2) {
    return PARSE_INVALID;
  }

  int dev = o["dev"].as<int>();
  if (dev != (int)deviceId) {
    return PARSE_IGNORED;
  }

  DisplayState next = state;
  next.dev = deviceId;

  if (o["seq"].is<uint32_t>()) {
    next.seq = o["seq"].as<uint32_t>();
  }

  if (o["lvl"].is<int>()) {
    next.level = constrain(o["lvl"].as<int>(), 0, 65535);
  }

  if (o["cap"].is<int>()) {
    next.capacity = constrain(o["cap"].as<int>(), 1, 65535);
  }

  if (o["state"].is<int>()) {
    int s = o["state"].as<int>();
    if (s >= 0 && s <= 5) {
      next.pump = static_cast<PumpState>(s);
    }
  }

  if (o["w"].is<int>()) {
    next.wear = constrain(o["w"].as<int>(), 0, 1000);
  }

  if (o["flow"].is<float>()) {
    next.flow = o["flow"].as<float>();
  } else if (o["flow"].is<int>()) {
    next.flow = (float)o["flow"].as<int>();
  }

  if (o["max_flow"].is<float>()) {
    next.max_flow = o["max_flow"].as<float>();
  } else if (o["max_flow"].is<int>()) {
    next.max_flow = (float)o["max_flow"].as<int>();
  }

  if (o["alarm"].is<bool>()) {
    next.alarm = o["alarm"].as<bool>();
  } else if (o["alarm"].is<int>()) {
    next.alarm = (o["alarm"].as<int>() != 0);
  }

  if (o["airgap"].is<bool>()) {
    next.airgap = o["airgap"].as<bool>();
  } else if (o["airgap"].is<int>()) {
    next.airgap = (o["airgap"].as<int>() != 0);
  }

  if (o["available"].is<bool>()) {
    next.available = o["available"].as<bool>();
  } else if (o["available"].is<int>()) {
    next.available = (o["available"].as<int>() != 0);
  }

  next.lastPacketMs = now;
  next.hasPacket = true;
  state = next;
  return PARSE_VALID;
}
