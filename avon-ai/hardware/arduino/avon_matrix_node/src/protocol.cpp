#include "protocol.h"
#include <ArduinoJson.h>

static bool required(JsonVariantConst root, const char *key) { return !root[key].isUnbound() && !root[key].isNull(); }

ParseResult parsePacket(const char *line, uint8_t deviceId, DisplayState &state, unsigned long now) {
  JsonDocument doc;
  if (deserializeJson(doc, line) || !doc.is<JsonObject>()) return PARSE_INVALID;
  JsonObjectConst o = doc.as<JsonObjectConst>();
  if (!required(o,"v") || !required(o,"dev") || !required(o,"seq")) return PARSE_INVALID;
  if (o["v"].as<int>() != 1 || o["dev"].as<int>() != deviceId) return PARSE_IGNORED;

  DisplayState next;
  next.dev = deviceId;
  next.seq = o["seq"].as<uint32_t>();
  if (deviceId == 1) {
    const char *keys[] = {"lvl","cap","h","hh","p1","p2","al","il"};
    for (auto key : keys) if (!required(o,key)) return PARSE_INVALID;
    next.capacity = constrain(o["cap"].as<int>(),1,65535);
    next.level = constrain(o["lvl"].as<int>(),0,next.capacity);
    next.high = constrain(o["h"].as<int>(),0,next.capacity);
    next.highHigh = constrain(o["hh"].as<int>(),0,next.capacity);
    int p1=o["p1"], p2=o["p2"];
    if(p1<0||p1>5||p2<0||p2>5) return PARSE_INVALID;
    next.pump1=static_cast<PumpState>(p1); next.pump2=static_cast<PumpState>(p2);
    next.alarm=constrain(o["al"].as<int>(),0,3); next.interlock=o["il"].as<int>()!=0;
  } else if (deviceId == 2) {
    const char *keys[] = {"flow","max","rf","dir","lim"};
    for (auto key : keys) if (!required(o,key)) return PARSE_INVALID;
    next.maxFlow=constrain(o["max"].as<int>(),1,65535);
    next.flow=constrain(o["flow"].as<int>(),0,next.maxFlow);
    next.restriction=constrain(o["rf"].as<int>(),0,1000);
    next.direction=constrain(o["dir"].as<int>(),-1,1);
    int lim=o["lim"]; if(lim<0||lim>3) return PARSE_INVALID; next.limit=static_cast<LimitCause>(lim);
    next.alarm=required(o,"al")?constrain(o["al"].as<int>(),0,3):0;
  } else {
    const char *keys[] = {"flow","max","tf","bp"};
    for (auto key : keys) if (!required(o,key)) return PARSE_INVALID;
    next.maxFlow=constrain(o["max"].as<int>(),1,65535);
    next.flow=constrain(o["flow"].as<int>(),0,next.maxFlow);
    next.treatmentFactor=constrain(o["tf"].as<int>(),0,1000);
    next.backpressure=o["bp"].as<int>()!=0 || next.treatmentFactor<950;
    next.alarm=required(o,"al")?constrain(o["al"].as<int>(),0,3):0;
  }
  next.lastPacketMs=now; next.hasPacket=true; state=next;
  return PARSE_VALID;
}
