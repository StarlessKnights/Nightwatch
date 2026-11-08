#include "protocol.h"
#include "config.h"
#include <ArduinoJson.h>
#include <cstring>

static bool required(JsonVariantConst root, const char *key) { return !root[key].isUnbound() && !root[key].isNull(); }

ParseResult parsePacket(const char *line, uint8_t deviceId, DisplayState &state, unsigned long now) {
  JsonDocument doc;
  if (deserializeJson(doc, line) || !doc.is<JsonObject>()) return PARSE_INVALID;
  JsonObjectConst o = doc.as<JsonObjectConst>();
  if (!required(o,"v") || !required(o,"dev") || !required(o,"seq")) return PARSE_INVALID;
  if (o["v"].as<int>() != 1 || o["dev"].as<int>() != deviceId) return PARSE_IGNORED;

  const char *keys[] = {"pump", "state", "w", "available", "lvl", "cap"};
  for (auto key : keys) if (!required(o,key)) return PARSE_INVALID;
  const char *pump = o["pump"] | "";
  if (strcmp(pump, ASSIGNED_PUMP) != 0) return PARSE_IGNORED;
  int pumpState = o["state"].as<int>();
  if (pumpState < 0 || pumpState > 5) return PARSE_INVALID;
  DisplayState next;
  next.dev = deviceId;
  next.seq = o["seq"].as<uint32_t>();
  next.pump = static_cast<PumpState>(pumpState);
  next.wear = constrain(o["w"].as<int>(), 0, 1000);
  next.capacity = constrain(o["cap"].as<int>(), 1, 65535);
  next.level = constrain(o["lvl"].as<int>(), 0, next.capacity);
  next.available = o["available"].as<int>() != 0 && next.pump != PUMP_UNAVAILABLE;
  next.lastPacketMs=now; next.hasPacket=true; state=next;
  return PARSE_VALID;
}
