#include "framebuffer.h"
void Framebuffer::clear(){ memset(pixels,0,sizeof(pixels)); }
void Framebuffer::set(int x,int y,bool on){ if(x>=0&&x<12&&y>=0&&y<8)pixels[y][x]=on?1:0; }
void Framebuffer::hline(int a,int b,int y,bool on){ for(int x=a;x<=b;x++)set(x,y,on); }
void Framebuffer::vline(int x,int a,int b,bool on){ for(int y=a;y<=b;y++)set(x,y,on); }
void Framebuffer::pack(uint32_t out[3]) const {
  out[0]=out[1]=out[2]=0;
  for(int y=0;y<8;y++)for(int x=0;x<12;x++)if(pixels[y][x]){
    const int i=y*12+x; out[i/32] |= (uint32_t)1 << (31-(i%32));
  }
}
