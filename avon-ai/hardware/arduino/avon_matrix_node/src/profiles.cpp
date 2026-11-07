#include "profiles.h"
#include "config.h"

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
  // Device 1 is a full-width liquid level display. The lit body rises
  // from the bottom, while the top row of liquid travels as a wave.
  float fraction = s.capacity == 0 ? 0.0f : (float)s.level / (float)s.capacity;
  fraction = constrain(fraction, 0.0f, 1.0f);
  int fillRows = (int)(fraction * 8.0f + 0.5f);
  if (fillRows <= 0) return;

  int surface = 8 - fillRows;
  for (int y = surface + 1; y < 8; ++y) {
    // Slowly moving vertical shimmer keeps the body from looking static.
    for (int x = 0; x < 12; ++x) {
      bool shimmer = ((x + phase + y * 2) % 11) != 0;
      f.set(x, y, shimmer);
    }
  }

  // Animated surface crest. Adjacent lit cells form a wave that shifts
  // left-to-right rather than blinking the whole level at once.
  for (int x = 0; x < 12; ++x) {
    int crest = (x + phase) % 6;
    f.set(x, surface, crest != 0 && crest != 5);
  }

  // Two small droplets periodically break above the surface.
  if (surface > 0) {
    int drop = (phase / 2) % 12;
    f.set(drop, surface - 1, true);
    if ((phase % 8) == 0) f.set((drop + 5) % 12, surface - 1, true);
  }

  // Critical states alternate between the liquid level and a large warning
  // triangle so the alarm remains unmistakable on a monochrome 12x8 display.
  bool critical = s.level >= s.highHigh || s.alarm == 3;
  if (critical && ((now / 400) % 2 == 0)) {
    f.clear();
    f.set(6, 0);
    f.set(5, 1); f.set(7, 1);
    f.set(4, 2); f.set(8, 2);
    f.set(3, 3); f.set(9, 3);
    f.set(2, 4); f.set(10, 4);
    f.set(1, 5); f.set(11, 5);
    f.hline(0, 11, 6);
    // Exclamation mark: two lit pixels, one dark gap, then a dot.
    f.set(6, 2); f.set(6, 3);
    f.set(6, 5);
  }
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
