#include <Arduino.h>
#include <Arduino_LED_Matrix.h>
#include "config.h"
#include "model.h"
#include "protocol.h"
#include "framebuffer.h"
#include "profiles.h"

ArduinoLEDMatrix matrix;
DisplayState state;
Framebuffer fb;
char line[INPUT_LINE_MAX+1]; size_t lineLength=0; bool dropping=false;
unsigned long lastFrame=0; uint8_t phase=0;

static void acceptLine(unsigned long now){
  line[lineLength]='\0';
  ParseResult result=parsePacket(line,DEVICE_ID,state,now);
  if(result==PARSE_INVALID){digitalWrite(LED_BUILTIN,HIGH);}
  else if(result==PARSE_VALID){digitalWrite(LED_BUILTIN,LOW);}
  lineLength=0;
}

static void serialPump(unsigned long now){
  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'){if(!dropping&&lineLength)acceptLine(now);lineLength=0;dropping=false;continue;}
    if(c=='\r')continue;
    if(dropping)continue;
    if(lineLength>=INPUT_LINE_MAX){dropping=true;lineLength=0;continue;}
    line[lineLength++]=c;
  }
}

static void diagnostic(unsigned long now){
  fb.clear();
  if(!state.hasPacket){bool on=(now/500)%2==0;fb.set(2,3,on);fb.set(5,3,(now/500)%3==1);fb.set(8,3,(now/500)%3==2);}
  else {bool on=(now/400)%2==0;if(on){fb.hline(1,3,3);fb.hline(5,7,3);fb.hline(9,11,3);}}
}

void setup(){
  pinMode(LED_BUILTIN,OUTPUT);digitalWrite(LED_BUILTIN,LOW);
  Serial.begin(SERIAL_BAUD);matrix.begin();matrix.clear();
  const char *profile=DEVICE_ID==1?"tank":(DEVICE_ID==2?"pipeline":"treatment");
  Serial.print("AVON|HELLO|v=1|dev=");Serial.print(DEVICE_ID);Serial.print("|profile=");Serial.print(profile);Serial.print("|fw=");Serial.println(FIRMWARE_VERSION);
}

void loop(){
  unsigned long now=millis();serialPump(now);
#if CORNER_TEST
  if((uint32_t)(now-lastFrame)>=300){lastFrame=now;fb.clear();static uint8_t corner=0;int xs[]={0,11,11,0},ys[]={0,0,7,7};fb.set(xs[corner],ys[corner]);corner=(corner+1)%4;uint32_t packed[3];fb.pack(packed);matrix.loadFrame(packed);}
#else
  bool stale=!state.hasPacket||(uint32_t)(now-state.lastPacketMs)>=LINK_TIMEOUT_MS;
  unsigned long interval=FRAME_INTERVAL_MS;
  if(!stale&&DEVICE_ID!=1){uint16_t value=state.flow;interval=map(value,0,state.maxFlow,400,40);interval=constrain(interval,40,400);}
  if((uint32_t)(now-lastFrame)>=interval){lastFrame=now;phase++;if(stale)diagnostic(now);else renderProfile(state,fb,now,phase);uint32_t packed[3];fb.pack(packed);matrix.loadFrame(packed);}
#endif
}
