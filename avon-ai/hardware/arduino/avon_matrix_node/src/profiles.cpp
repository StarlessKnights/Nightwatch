#include "profiles.h"

static void pumpIcon(Framebuffer &f,int x,PumpState p,uint8_t phase,bool blink){
  if(p==PUMP_STOPPED){f.hline(x+1,x+2,4);return;}
  if(p==PUMP_TRIPPED||p==PUMP_UNAVAILABLE){
    if(p==PUMP_UNAVAILABLE){f.hline(x,x+3,1);f.hline(x,x+3,6);f.vline(x,1,6);f.vline(x+3,1,6);}
    if(!blink||phase%2==0){f.set(x,2);f.set(x+3,2);f.set(x+1,3);f.set(x+2,3);f.set(x+1,4);f.set(x+2,4);f.set(x,5);f.set(x+3,5);}return;
  }
  if(p==PUMP_STARTING){int r=(phase%4);f.set(x+1+(r&1),3+(r>>1));return;}
  if(p==PUMP_DEGRADED&&phase%2)return;
  switch(phase%4){case 0:f.hline(x,x+3,4);break;case 1:f.vline(x+2,2,5);break;case 2:f.hline(x,x+3,3);break;default:f.vline(x+1,2,5);}
}

static void tank(const DisplayState&s,Framebuffer&f,unsigned long now,uint8_t phase){
  f.vline(0,0,7);f.vline(3,0,7);f.hline(0,3,7);
  int fill=(int)((uint32_t)s.level*8/s.capacity);for(int row=0;row<fill;row++)f.hline(1,2,6-row);
  bool hh=s.level>=s.highHigh||s.alarm==3;bool h=s.level>=s.high||s.alarm==2;
  if(hh){if((now/100)%2==0){for(int y=0;y<8;y++)f.set(1,y);f.set(2,0);f.set(2,1);f.set(2,3);f.set(2,4);f.set(2,6);}}
  else if(h&&((now/250)%2==0))f.hline(1,2,0);
  if(s.interlock)f.hline(0,3,1);
  pumpIcon(f,4,s.pump1,phase,phase%2==0);pumpIcon(f,8,s.pump2,phase,phase%2==0);
}

static void pipeline(const DisplayState&s,Framebuffer&f,uint8_t phase,unsigned long now){
  f.hline(0,11,2);f.hline(0,11,5);
  if(s.direction==0||s.flow==0)return;
  int density=map(s.flow,0,s.maxFlow,1,4);
  for(int i=0;i<density;i++){int x=(phase*2+i*4)%12;if(s.direction<0)x=11-x;f.set(x,3);f.set(x,4);}
  bool restriction=s.restriction<950||s.limit==LIMIT_PIPELINE;
  if(restriction&&((now/166)%2==0)){f.vline(5,1,6);f.vline(6,1,6);}
  if(s.limit==LIMIT_TREATMENT){f.vline(10,1,6);f.vline(11,1,6);}
  if(s.limit==LIMIT_VOLUME)f.vline(0,1,6);
  if(s.alarm>=2)f.hline(0,11,0,(now/250)%2==0);
}

static void treatment(const DisplayState&s,Framebuffer&f,uint8_t phase,unsigned long now){
  f.hline(0,7,3);f.hline(0,7,4);
  bool bp=s.backpressure||s.treatmentFactor<950;
  if(bp){bool on=(now/166)%2==0;if(on){f.vline(9,1,6);f.vline(11,1,6);}for(int i=0;i<3;i++){int x=8-((phase*2+i*4)%9);f.set(x,3);f.set(x,4);}if(s.alarm==3&&(now/100)%2==0)f.hline(0,11,0);}
  else {for(int i=0;i<3;i++){int x=(phase*2+i*4)%9;f.set(x,3);f.set(x,4);}int r=phase%4;f.set(9+(r&1),2+(r>>1));f.set(10,3);f.set(9+(r&1),4+(r>>1));}
}

void renderProfile(const DisplayState&s,Framebuffer&f,unsigned long now,uint8_t phase){f.clear();if(DEVICE_ID==1)tank(s,f,now,phase);else if(DEVICE_ID==2)pipeline(s,f,phase,now);else treatment(s,f,phase,now);}
