"""Original Atari Lynx cartridge generator, cc65/65C02 + hardware TGI."""
from __future__ import annotations

LYNX_SOURCE=r'''/* Dragon Lynx Quest: original Atari Lynx game, not SDL/WebView.
   65C02 CPU, Suzy/Mikey screen via Lynx native TGI driver.
   160x102 colour framebuffer and hardware D-pad + A/B buttons.
   Collection victory, pursuits, shield cooldown, score and reset. */
#include <lynx.h>
#include <joystick.h>
#include <tgi.h>
#include <6502.h>
#include <stdio.h>
#define FOES 3
static unsigned char x,y,gemx,gemy,hp,score,chapter,tick,guard,won;
static unsigned char ex[FOES],ey[FOES];
static unsigned int rng=__SEED__;
static char hud[42];

static unsigned int rng_next(void){
 rng^=rng<<7;rng^=rng>>9;rng^=rng<<8;return rng;
}
static void new_game(void){
 unsigned char i;
 rng=__SEED__;x=17;y=50;gemx=111;gemy=60;
 hp=5;score=0;chapter=1;tick=0;guard=0;won=0;
 for(i=0;i<FOES;i++){ex[i]=(unsigned char)(139-i*24);ey[i]=(unsigned char)(19+i*31);}
}
static void box(int bx,int by,int w,unsigned char col){
 tgi_setcolor(col);tgi_bar(bx,by,bx+w,by+w);
}
static void redraw(void){
 unsigned char i;
 tgi_clear();
 tgi_setcolor(COLOR_WHITE);
 sprintf(hud,"DRAGON LYNX %u/20 HP%u",score,hp);
 tgi_outtextxy(2,2,hud);
 tgi_setcolor(COLOR_BLUE);
 tgi_line(1,12,158,12);
 box(gemx,gemy,6,COLOR_YELLOW);
 for(i=0;i<FOES;i++)box(ex[i],ey[i],7,COLOR_RED);
 if(!guard||tick%8<4)box(x,y,8,COLOR_GREEN);
 if(won){tgi_setcolor(COLOR_WHITE);tgi_outtextxy(8,43,"VICTORY - A AGAIN");}
 else if(!hp){tgi_setcolor(COLOR_WHITE);tgi_outtextxy(8,43,"DRAGON DOWN - A");}
 tgi_updatedisplay();
 while(tgi_busy()){}
}
static void play(unsigned char buttons){
 unsigned char i,rate;
 if(!hp||won){if(buttons&JOY_BTN_A_MASK)new_game();return;}
 if((buttons&JOY_LEFT_MASK)&&x>2)x--;
 if((buttons&JOY_RIGHT_MASK)&&x<148)x++;
 if((buttons&JOY_UP_MASK)&&y>16)y--;
 if((buttons&JOY_DOWN_MASK)&&y<91)y++;
 if(guard)guard--;
 if(x+8>=gemx&&x<=gemx+6&&y+8>=gemy&&y<=gemy+6){
  score++;chapter=(unsigned char)(1+score/4);
  gemx=(unsigned char)(8+rng_next()%141);
  gemy=(unsigned char)(17+rng_next()%75);
  if(score%5==0&&hp<5)hp++;
  if(score>=20)won=1;
 }
 tick++;
 for(i=0;i<FOES;i++){
  rate=(unsigned char)(12+i*2-(chapter>8?8:chapter));
  if(tick%rate==0){
   if(ex[i]<x)ex[i]++;else if(ex[i]>x)ex[i]--;
   if(ey[i]<y)ey[i]++;else if(ey[i]>y)ey[i]--;
  }
  if(x+8>=ex[i]&&x<=ex[i]+7&&y+8>=ey[i]&&y<=ey[i]+7&&!guard){
   hp--;guard=37;ex[i]=(unsigned char)(131-i*18);ey[i]=(unsigned char)(17+i*24);
  }
 }
}
int main(void){
 unsigned char buttons;
 tgi_install(tgi_static_stddrv);
 tgi_init();
 if(tgi_geterror()!=0)return 1;
 CLI();
 while(tgi_busy()){}
 if(joy_install(joy_static_stddrv)!=JOY_ERR_OK)return 2;
 new_game();
 for(;;){
  buttons=joy_read(JOY_1);play(buttons);
  if(tick%2==0||!hp||won)redraw();
 }
 return 0;
}
'''
MAKEFILE="""\
CL65 ?= cl65
all: build/dragon.lnx
build/dragon.lnx: src/main.c
\tmkdir -p build
\t$(CL65) -t lynx -O -o $@ $<
clean:
\trm -rf build
"""
def lynx_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Dragon Lynx seed must be uint32")
    value=(seed&65535) or 1
    return {
      "src/main.c":LYNX_SOURCE.replace("__SEED__",str(value)),
      "Makefile":MAKEFILE,
      "README.port.md":(
        "# Dragon Lynx Quest, original 65C02 source\n\n"
        "Native Atari Lynx TGI 160x102 colour display, static joypad driver, "
        "three pursuers, life/score, invulnerability and a 20-crystal victory. "
        "Make builds .lnx only if the actual cc65 target compiler and linker "
        "complete successfully. No firmware, games or art bundled. Suzy "
        "timing, Mikey audio and real hardware controls remain unverified.\n"
      )
    }
