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
  if(strcmp(line,"AVON|IDENTIFY")==0){
    Serial.print("AVON|HELLO|v=1|dev=");Serial.print(DEVICE_ID);
    Serial.print("|profile=pump|fw=");Serial.println(FIRMWARE_VERSION);
    lineLength=0;return;
  }
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

static void buildApiTestFrame(){
  fb.clear();
  for(int x=0;x<12;x++){fb.set(x,0);fb.set(x,7);}
  for(int y=0;y<8;y++){fb.set(0,y);fb.set(11,y);}
  for(int i=1;i<7;i++){fb.set(i,i);fb.set(11-i,i);}
}

static void printApiTestFrame(){
  Serial.println("FRAME_BEGIN");
  for(int y=0;y<8;y++){for(int x=0;x<12;x++)Serial.print(fb.pixels[y][x]?'#':'.');Serial.println();}
  uint32_t packed[3];fb.pack(packed);
  Serial.print("PACKED ");for(int i=0;i<3;i++){Serial.print("0x");Serial.print(packed[i],HEX);if(i<2)Serial.print(' ');}Serial.println();
  Serial.println("FRAME_END");
}

void setup(){
  pinMode(LED_BUILTIN,OUTPUT);digitalWrite(LED_BUILTIN,LOW);
  Serial.begin(SERIAL_BAUD);matrix.begin();matrix.clear();
  const char *profile="pump";
  Serial.print("AVON|HELLO|v=1|dev=");Serial.print(DEVICE_ID);Serial.print("|profile=");Serial.print(profile);Serial.print("|fw=");Serial.println(FIRMWARE_VERSION);
}

void loop(){
  unsigned long now=millis();serialPump(now);
#if API_TEST
  if((uint32_t)(now-lastFrame)>=2000){
    lastFrame=now;buildApiTestFrame();static bool usePacked=false;usePacked=!usePacked;
    printApiTestFrame();uint32_t packed[3];fb.pack(packed);
    if(usePacked){Serial.println("DISPLAY_API loadFrame");matrix.loadFrame(packed);}
    else {Serial.println("DISPLAY_API loadPixels");matrix.loadPixels(&fb.pixels[0][0],96);}
  }
#elif MINIMAL_TEST
  if((uint32_t)(now-lastFrame)>=500){
    lastFrame=now; fb.clear();
    // Fixed tank rectangle: rails at x=0/3 and four-row fill.
    for(int y=0;y<8;y++){fb.set(0,y);fb.set(3,y);}
    for(int y=4;y<7;y++){fb.set(1,y);fb.set(2,y);}
    // Fixed pump ring on the right.
    fb.hline(6,9,1);fb.hline(6,9,6);fb.vline(6,1,6);fb.vline(9,1,6);
    fb.set(7,3);fb.set(8,3);fb.set(7,4);fb.set(8,4);
    matrix.loadPixels(&fb.pixels[0][0],96);
  }
#elif CORNER_TEST
  if((uint32_t)(now-lastFrame)>=300){lastFrame=now;fb.clear();static uint8_t corner=0;int xs[]={0,11,11,0},ys[]={0,0,7,7};fb.set(xs[corner],ys[corner]);corner=(corner+1)%4;matrix.loadPixels(&fb.pixels[0][0],96);}
#else
  bool stale=!state.hasPacket||(uint32_t)(now-state.lastPacketMs)>=LINK_TIMEOUT_MS;
  if((uint32_t)(now-lastFrame)>=FRAME_INTERVAL_MS){lastFrame=now;phase++;if(stale)diagnostic(now);else renderProfile(state,fb,now,phase);matrix.loadPixels(&fb.pixels[0][0],96);}
#endif
}
