"""Original Sega Dreamcast and Sony PlayStation 2 open-SDK native games.

Dreamcast uses KallistiOS Maple controllers and SH-4 video VRAM.
PS2 uses ps2sdk's RPC controller and gsKit's Graphics Synthesizer.

These are lawful independent homebrew source programs, not vendor-supplied
ROMs, title content, proprietary SDK blobs, or fabricated executable files.
Build and hardware verification must happen on real target SDK runners.
"""
from __future__ import annotations

def _seed(seed:int)->int:
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("original console source seed must be uint32")
    return seed or 1

DREAMCAST=r'''/* Original Dragon Dreamcast collectible survival, KallistiOS SH-4.
   Direct hardware RGB565 framebuffer + Maple controller, no SDL or browser. */
#include <kos.h>
#include <stdint.h>
#include <stdlib.h>
#define W 320
#define H 240
#define FOES 4
static int x=40,y=80,starx=190,stary=135,hp=5,score=0,stage=1,tick=0,shield=0;
static int ex[FOES]={259,283,227,211},ey[FOES]={45,81,180,150};
static uint32_t rng=__SEED__u;
static uint32_t rnd(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static uint16_t color(int red,int green,int blue) {
 return (uint16_t)(((red>>3)<<11)|((green>>2)<<5)|(blue>>3));
}
static void clear(uint16_t fill) {
 for(int i=0;i<W*H;i++)vram_s[i]=fill;
}
static void box(int x0,int y0,int width,int height,uint16_t ink) {
 for(int y1=0;y1<height;y1++) {
  int py=y0+y1;
  if(py<0||py>=H)continue;
  for(int x1=0;x1<width;x1++) {
   int px=x0+x1;
   if(px>=0&&px<W)vram_s[py*W+px]=ink;
  }
 }
}
static void reset(void){
 rng=__SEED__u;x=40;y=80;starx=190;stary=135;
 hp=5;score=0;stage=1;tick=0;shield=0;
 for(int i=0;i<FOES;i++){ex[i]=259-i*13;ey[i]=45+i*42;}
}
static void update(int dx,int dy,int restart) {
 if(restart){reset();return;}
 if(!hp)return;
 x+=dx;y+=dy;
 if(x<9)x=9;if(y<21)y=21;
 if(x>W-27)x=W-27;if(y>H-29)y=H-29;
 if(abs(x-starx)<16&&abs(y-stary)<16) {
  score++;stage=1+score/4;starx=13+(int)(rnd()%286);
  stary=25+(int)(rnd()%192);
  if(score%5==0&&hp<5)hp++;
 }
 tick++;if(shield)shield--;
 for(int i=0;i<FOES;i++){
  int cycle=20+i*5-(stage>12?12:stage);
  if(tick%cycle==0){
   if(ex[i]<x)ex[i]++;else if(ex[i]>x)ex[i]--;
   if(ey[i]<y)ey[i]++;else if(ey[i]>y)ey[i]--;
  }
  if(abs(ex[i]-x)<16&&abs(ey[i]-y)<16&&!shield){
   hp--;shield=45;
   ex[i]=275-i*13;ey[i]=205-i*32;
  }
 }
}
static void paint(void) {
 clear(color(17,22,45));
 for(int n=0;n<10;n++)box(0,n*24+5,W,1,color(37,48,74));
 box(starx,stary,15,15,color(247,209,83));
 box(starx+5,stary+3,5,7,color(255,247,175));
 for(int n=0;n<FOES;n++){
  box(ex[n],ey[n],18,18,color(222,75,96));
  box(ex[n]+5,ey[n]+5,4,4,color(29,31,44));
 }
 if(shield==0||tick%8<4) {
  box(x,y,19,19,color(86,226,155));
  box(x+12,y+4,4,4,color(20,53,44));
 }
 for(int n=0;n<hp;n++)box(7+n*21,6,15,8,color(243,95,119));
 for(int n=0;n<(score>25?25:score);n++)
  box(W-8-n*10,6,7,7,color(246,206,89));
 if(!hp)box(65,96,190,48,color(155,33,80));
}
int main(int argc,char**argv) {
 (void)argc;(void)argv;
 vid_set_mode(DM_320x240_NTSC,PM_RGB565);
 reset();
 int old_a=0;
 for(;;){
  maple_device_t*dev=maple_enum_type(0,MAPLE_FUNC_CONTROLLER);
  cont_state_t*pad=dev?(cont_state_t*)maple_dev_status(dev):NULL;
  int dx=0,dy=0,restart=0;
  if(pad) {
   if(pad->buttons&CONT_START)break;
   dx=2*(!!(pad->buttons&CONT_DPAD_RIGHT))-2*(!!(pad->buttons&CONT_DPAD_LEFT));
   dy=2*(!!(pad->buttons&CONT_DPAD_DOWN))-2*(!!(pad->buttons&CONT_DPAD_UP));
   if(pad->joyx>25)dx+=2;if(pad->joyx< -25)dx-=2;
   if(pad->joyy>25)dy+=2;if(pad->joyy< -25)dy-=2;
   int a=!!(pad->buttons&CONT_A);
   restart=a&&!old_a;old_a=a;
  }else old_a=0;
  update(dx,dy,restart);
  paint();
  thd_sleep(16);
 }
 return 0;
}
'''
DREAMCAST_MAKE=r'''# Original KallistiOS SH-4 native game. Requires sourced KOS environment.
ifeq ($(strip $(KOS_BASE)),)
$(error Install/supply KallistiOS KOS_BASE and SH-4 toolchain)
endif
TARGET = dragon_dreamcast.elf
OBJS = build/main.o
include $(KOS_BASE)/Makefile.rules
all: $(TARGET)
build/main.o: src/main.c
	@mkdir -p build
	$(KOS_CC) $(KOS_CFLAGS) -c $< -o $@
$(TARGET): $(OBJS)
	$(KOS_CC) $(KOS_CFLAGS) $(KOS_LDFLAGS) -o $@ $(OBJS) $(KOS_LIBS)
clean:
	rm -rf build $(TARGET)
'''

PS2=r'''/* Original Dragon PS2 homebrew for ps2sdk + gsKit (MIPS EE / GS).
   Controller RPC and gsKit primitives, NOT Windows GDI/SDL or Sony SDK. */
#include <tamtypes.h>
#include <sifrpc.h>
#include <libpad.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define FOES 4
static unsigned char pad_storage[256] __attribute__((aligned(64)));
static int x=50,y=65,sx=340,sy=220,hp=5,score=0,stage=1,tick=0,shield=0;
static int ex[FOES]={500,480,520,450},ey[FOES]={80,150,300,350};
static uint32_t rng=__SEED__u;
static uint32_t next_rng(void) {
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void) {
 rng=__SEED__u;x=50;y=65;sx=340;sy=220;hp=5;score=0;stage=1;tick=0;shield=0;
 for(int i=0;i<FOES;i++){ex[i]=500-i*18;ey[i]=80+i*76;}
}
static void update(int dx,int dy,int restart) {
 if(restart){reset();return;}
 if(!hp)return;
 x+=dx;y+=dy;
 if(x<8)x=8;if(y<15)y=15;
 if(x>608)x=608;if(y>422)y=422;
 if(abs(x-sx)<27&&abs(y-sy)<27){
  score++;stage=1+score/4;sx=24+(int)(next_rng()%560);
  sy=30+(int)(next_rng()%375);
  if(score%5==0&&hp<5)hp++;
 }
 tick++;if(shield)shield--;
 for(int i=0;i<FOES;i++){
  int period=16+i*6-(stage>11?11:stage);
  if(tick%period==0){
   if(x>ex[i])ex[i]+=2;else if(x<ex[i])ex[i]-=2;
   if(y>ey[i])ey[i]+=2;else if(y<ey[i])ey[i]-=2;
  }
  if(abs(x-ex[i])<27&&abs(y-ey[i])<27&&!shield){
   hp--;shield=45;
   ex[i]=525-i*22;ey[i]=385-i*61;
  }
 }
}
static void rectangle(GSGLOBAL*g,int x0,int y0,int width,int height,
                      int z,u64 ink){
 gsKit_prim_sprite(g,(float)x0,(float)y0,
                   (float)(x0+width),(float)(y0+height),z,ink);
}
static void draw(GSGLOBAL*screen){
 u64 bg=GS_SETREG_RGBAQ(14,22,45,0,0);
 u64 grid=GS_SETREG_RGBAQ(41,59,80,0,0);
 u64 star=GS_SETREG_RGBAQ(250,205,95,0,0);
 u64 dragon=GS_SETREG_RGBAQ(83,225,153,0,0);
 u64 foe=GS_SETREG_RGBAQ(216,75,104,0,0);
 gsKit_clear(screen,bg);
 for(int i=0;i<12;i++)rectangle(screen,0,i*36,640,1,1,grid);
 rectangle(screen,sx,sy,22,22,2,star);
 for(int i=0;i<FOES;i++)rectangle(screen,ex[i],ey[i],24,24,2,foe);
 if(!shield||tick%8<4)rectangle(screen,x,y,23,23,3,dragon);
 for(int i=0;i<hp;i++)rectangle(screen,12+i*28,7,20,10,4,foe);
 for(int i=0;i<(score>30?30:score);i++)
  rectangle(screen,634-i*12,7,9,9,4,star);
 if(!hp)rectangle(screen,210,170,225,90,5,foe);
 gsKit_queue_exec(screen);
 gsKit_sync_flip(screen);
 gsKit_queue_reset(screen->Per_Queue);
}
int main(int argc,char**argv) {
 (void)argc;(void)argv;
 SifInitRpc(0);
 padInit(0);
 int pad_open=padPortOpen(0,0,pad_storage);
 GSGLOBAL*screen=gsKit_init_global();
 if(!screen)return 2;
 screen->ZBuffering=GS_SETTING_OFF;
 dmaKit_init(D_CTRL_RELE_OFF,D_CTRL_MFD_OFF,D_CTRL_STS_UNSPEC,
             D_CTRL_STD_OFF,D_CTRL_RCYC_8,1<<DMA_CHANNEL_GIF);
 dmaKit_chan_init(DMA_CHANNEL_GIF);
 gsKit_init_screen(screen);
 gsKit_mode_switch(screen,GS_ONESHOT);
 reset();
 int old_cross=0;
 while(1){
  int dx=0,dy=0,restart=0;
  if(pad_open&&padGetState(0,0)==PAD_STATE_STABLE){
   struct padButtonStatus st;
   if(padRead(0,0,&st)){
    u32 keys=0xffff^(u32)st.btns;
    if(keys&PAD_START)break;
    dx=3*(!!(keys&PAD_RIGHT))-3*(!!(keys&PAD_LEFT));
    dy=3*(!!(keys&PAD_DOWN))-3*(!!(keys&PAD_UP));
    int cross=!!(keys&PAD_CROSS);
    restart=cross&&!old_cross;old_cross=cross;
   }
  }
  update(dx,dy,restart);
  draw(screen);
 }
 if(pad_open)padPortClose(0,0);
 padEnd();
 return 0;
}
'''
PS2_MAKE=r'''# Open PS2SDK homebrew + gsKit. No proprietary Sony developer tools.
ifeq ($(strip $(PS2SDK)),)
$(error PS2SDK environment and installed ee/startup are required)
endif
ifeq ($(strip $(GSKIT)),)
$(error GSKIT environment with headers/lib installed is required)
endif
EE_BIN := dragon_ps2.elf
EE_OBJS := src/main.o
EE_CFLAGS += -I$(GSKIT)/include
EE_LDFLAGS += -L$(GSKIT)/lib
EE_LIBS := -lpad -lgskit -ldmakit -lm
all: $(EE_BIN)
include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
clean:
	rm -f $(EE_BIN) $(EE_OBJS)
'''

def dreamcast_source(seed:int)->dict[str,str]:
    n=_seed(seed)
    return {
      "src/main.c":DREAMCAST.replace("__SEED__",str(n)),
      "Makefile":DREAMCAST_MAKE,
      "README.port.md":"# Original Sega Dreamcast KallistiOS game\n"
        "SH-4 direct 320x240 RGB565 VRAM, Maple controller D-pad/analog/A/Start, "
        "four enemies, damage cooldown, health and score progression. "
        "Source-only KOS ELF: real KOS compiler and Flycast/device validation pending.\n",
    }

def ps2_source(seed:int)->dict[str,str]:
    n=_seed(seed)
    return {
      "src/main.c":PS2.replace("__SEED__",str(n)),
      "Makefile":PS2_MAKE,
      "README.port.md":"# Original PlayStation 2 PS2SDK/gsKit game\n"
        "MIPS EE graphics via gsKit Graphics Synthesizer/DMA and SIF pad RPC, "
        "four enemies, points, health and restart. Open-source PS2SDK target ELF, "
        "requires devkit/gsKit and PCSX2 or physical validation; no Sony SDK.\n",
    }
