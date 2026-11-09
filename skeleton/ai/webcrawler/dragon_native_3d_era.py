"""Original 3D-era Nintendo 64, dual-screen Nintendo DS and Sony PSP games.

Source-only adapters: libdragon (VR4300/RDP display and N64 controller),
libnds (ARM9 primary bitmap + touchscreen/ARM7 service via devkitPro),
PSPSDK (Allegrex PSP LCD + analog/buttons). These are independent native
game loops with game state, scoring, failure and reset, not SDL/HTML skins.

No Nintendo/Sony proprietary SDK, firmware, games, assets or BIOS included.
"""
from __future__ import annotations

def _seed(seed:int)->int:
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("deterministic native uint32 game seed required")
    return seed

def n64_source(seed:int)->dict[str,str]:
    seed=_seed(seed)
    # Uses current libdragon display surface API (not obsolete display_lock).
    code=r'''/* Original N64 homebrew: actual libdragon 320x240 surface and joypad. */
#include <libdragon.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#define W 320
#define H 240
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
static int x=38,y=46,gemx=__GEMX__,gemy=__GEMY__;
static int foe_x=250,foe_y=140,score=0,hp=4,level=1,blink=0;
static uint32_t rng=__SEED__u;
static int rnd(int n){
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (int)(rng%(uint32_t)n);
}
static void reset(void){
 rng=__SEED__u;x=38;y=46;gemx=__GEMX__;gemy=__GEMY__;
 foe_x=250;foe_y=140;score=0;hp=4;level=1;blink=0;
}
static void draw(surface_t *display){
 graphics_fill_screen(display,graphics_make_color(14,23,49,255));
 const uint32_t floor_color=graphics_make_color(44,58,84,255);
 for(int j=0;j<9;j++)
  graphics_draw_box(display,12,18+j*24,296,1,floor_color);
 for(int j=0;j<12;j++)
  graphics_draw_box(display,16+j*24,14,1,214,floor_color);
 graphics_draw_box(display,gemx,gemy,12,12,
   graphics_make_color(237,205,83,255));
 graphics_draw_box(display,gemx+4,gemy+3,4,5,
   graphics_make_color(255,247,167,255));
 graphics_draw_box(display,foe_x,foe_y,19,18,
   graphics_make_color(221,74,101,255));
 graphics_draw_box(display,foe_x+5,foe_y+5,4,4,
   graphics_make_color(36,37,57,255));
 if(!blink||(blink%8)<4){
  graphics_draw_box(display,x,y,18,18,
    graphics_make_color(84,222,161,255));
  graphics_draw_box(display,x+12,y+2,8,6,
    graphics_make_color(118,248,183,255));
  graphics_draw_box(display,x+14,y+4,3,3,
    graphics_make_color(21,48,48,255));
 }
 for(int i=0;i<hp;i++)graphics_draw_box(display,15+i*22,6,16,8,
   graphics_make_color(235,87,107,255));
 for(int i=0;i<MIN(15,score);i++)
  graphics_draw_box(display,304-i*12,6,8,8,
    graphics_make_color(251,207,92,255));
 if(!hp)graphics_draw_box(display,70,93,180,55,
   graphics_make_color(161,32,74,255));
}
int main(void){
 display_init(RESOLUTION_320x240,DEPTH_16_BPP,2,GAMMA_NONE,FILTERS_RESAMPLE);
 joypad_init();
 for(;;){
  joypad_poll();
  joypad_inputs_t controller=joypad_get_inputs(JOYPAD_PORT_1);
  if(!hp&&controller.btn.a)reset();
  if(hp){
   int dx=(controller.btn.d_right?2:0)-(controller.btn.d_left?2:0);
   int dy=(controller.btn.d_down?2:0)-(controller.btn.d_up?2:0);
   if(abs(controller.stick_x)>15)dx+=controller.stick_x/30;
   if(abs(controller.stick_y)>15)dy-=controller.stick_y/30;
   x=MAX(14,MIN(W-34,x+dx));
   y=MAX(19,MIN(H-35,y+dy));
   if(x<gemx+12&&x+18>gemx&&y<gemy+12&&y+18>gemy){
    score++;level=1+score/5;
    gemx=23+rnd(260);gemy=25+rnd(186);
    if(score%5==0)hp=MIN(hp+1,5);
   }
   int enemy_speed=1+MIN(level/3,3);
   foe_x+=(x>foe_x?enemy_speed:-enemy_speed);
   foe_y+=(y>foe_y?enemy_speed:-enemy_speed);
   if(abs(x-foe_x)<17&&abs(y-foe_y)<17){
    if(blink==0){hp--;blink=40;}
   }
   if(blink)blink--;
  }
  surface_t*display=display_get();
  draw(display);
  display_show(display);
 }
 return 0;
}
'''
    code=(code.replace("__SEED__",str(seed or 1))
              .replace("__GEMX__",str(90+seed%130))
              .replace("__GEMY__",str(35+seed%150)))
    make="""\
N64_INST ?= /opt/libdragon
BUILD_DIR := build
SOURCE_DIR := src
N64_ROM_TITLE := DRAGON QUEST N64
include $(N64_INST)/include/n64.mk
.PHONY: all clean
all: dragon.z64
build/main.o: src/main.c
	mkdir -p build
	$(N64_CC) $(N64_CFLAGS) -c $< -o $@
build/dragon.elf: build/main.o
	$(N64_CC) -o $@ $^ $(N64_LDFLAGS)
dragon.z64: build/dragon.elf
	$(N64_OBJCOPY) -O binary $< $<.bin
	$(N64_TOOL) $(N64_TOOLFLAGS) --size 1M --output $@ $<.bin
	$(N64_CHKSUM) $@
clean:
	rm -rf build dragon.z64
"""
    return {"src/main.c":code,"Makefile":make}

def ds_source(seed:int)->dict[str,str]:
    seed=_seed(seed)
    code=r'''/* Original Nintendo DS: upper ARM9 bitmap playfield, touchscreen aim,
  lower-screen text, D-pad input, VBlank and separate ARM7 service via libnds. */
#include <nds.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#define W 256
#define H 192
#define CLAMP(n,a,b) ((n)<(a)?(a):((n)>(b)?(b):(n)))
static u16* pixels;
static int x=32,y=100,star_x=__STAR_X__,star_y=__STAR_Y__;
static int score=0,stage=1,life=5,frames=0,invuln=0;
static unsigned int rng=__SEED__u;
static unsigned int next_rand(void){
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void draw_box(int px,int py,int width,int height,u16 color){
 for(int j=0;j<height;j++){
  int yy=py+j;
  if(yy<0||yy>=H)continue;
  for(int i=0;i<width;i++){
   int xx=px+i;
   if(xx>=0&&xx<W)pixels[yy*256+xx]=color;
  }
 }
}
static void clear_screen(void){
 for(int i=0;i<W*H;i++)pixels[i]=ARGB16(1,3,5,11);
}
static void reset(void){
 x=32;y=100;star_x=__STAR_X__;star_y=__STAR_Y__;
 score=0;stage=1;life=5;frames=0;invuln=0;
 rng=__SEED__u;
}
int main(void){
 /* The bottom display owns the libnds console and touch controls. */
 consoleDemoInit();
 videoSetMode(MODE_5_2D);
 vramSetBankA(VRAM_A_MAIN_BG);
 int bg=bgInit(3,BgType_Bmp16,BgSize_B16_256x256,0,0);
 pixels=bgGetGfxPtr(bg);
 reset();
 while(pmMainLoop()){
  scanKeys();
  u32 keys=keysHeld(),pressed=keysDown();
  touchPosition touch;
  touchRead(&touch);
  if(pressed&KEY_START)reset();
  if((keys&KEY_LEFT)&&x>5)x--;
  if((keys&KEY_RIGHT)&&x<241)x++;
  if((keys&KEY_UP)&&y>5)y--;
  if((keys&KEY_DOWN)&&y<175)y++;
  /* Touchscreen coordinates refer to the bottom screen. Touch to cast
     a ranged rescue pulse towards the matching projected target. */
  if(pressed&KEY_TOUCH){
   int tx=(int)touch.px,ty=(int)touch.py;
   if(abs(tx-star_x)<19&&abs(ty-star_y)<19){
    score+=2;star_x=12+(next_rand()%220);
    star_y=18+(next_rand()%150);stage++;
   }
  }
  if(abs(x-star_x)<12&&abs(y-star_y)<12){
   score++;stage++;star_x=12+(next_rand()%220);
   star_y=18+(next_rand()%150);
   life=CLAMP(life+1,0,5);
  }
  if(invuln)invuln--;
  if(frames%80==0 && frames>0 && !invuln && stage>2){
   int hazard_x=20+(frames/80*31)%210;
   if(abs(hazard_x-x)<22){life--;invuln=45;}
  }
  if(!life){
   if(pressed&KEY_A)reset();
  }
  clear_screen();
  for(int i=0;i<12;i++)draw_box(4+i*21,23,1,160,ARGB16(1,5,8,13));
  draw_box(star_x,star_y,12,12,ARGB16(1,31,25,5));
  draw_box(star_x+4,star_y+3,4,5,ARGB16(1,31,31,23));
  if(!invuln||(frames%8)<4){
   draw_box(x,y,16,16,ARGB16(1,8,29,14));
   draw_box(x+10,y+3,3,3,ARGB16(1,0,3,2));
  }
  for(int i=0;i<life;i++)
   draw_box(6+i*19,6,13,9,ARGB16(1,31,7,11));
  if(!life)draw_box(56,69,145,52,ARGB16(1,21,4,6));
  if(frames%18==0){
   iprintf("\\x1b[0;0H DRAGON DS ORIGINAL\\n");
   iprintf("Score: %d   Stage: %d\\n",score,stage);
   iprintf("Lives: %d\\n",life);
   iprintf("Move: D-PAD\\nTouch target to cast\\n");
   iprintf("START reset / A revive\\n");
  }
  frames++;
  swiWaitForVBlank();
 }
 return 0;
}
'''
    code=(code.replace("__SEED__",str(seed or 1))
          .replace("__STAR_X__",str(45+seed%164))
          .replace("__STAR_Y__",str(35+(seed//17)%105)))
    # Build separately using the official devkitPro nds_rules target with
    # standard ARM9/ARM7 structure, rather than reusing GBA output.
    make="""\
.SUFFIXES:
ifeq ($(strip $(DEVKITARM)),)
$(error DEVKITARM is required: install devkitPro's Nintendo DS toolchain)
endif
include $(DEVKITARM)/ds_rules
TARGET := dragon_ds
BUILD := build
SOURCES := src
INCLUDES := include
ARCH := -march=armv5te -mtune=arm946e-s -mthumb
CFLAGS := -Wall -O2 -ffunction-sections -fdata-sections $(ARCH) $(INCLUDE) -DARM9
LDFLAGS := -specs=ds_arm9.specs $(ARCH) -Wl,-Map,$(notdir $*.map)
LIBS := -lnds9
LIBDIRS := $(LIBNDS)
ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT := $(CURDIR)/$(TARGET)
export VPATH := $(CURDIR)/src
export DEPSDIR := $(CURDIR)/$(BUILD)
CFILES := $(notdir $(wildcard src/*.c))
export OFILES := $(CFILES:.c=.o)
export INCLUDE := -I$(CURDIR)/include -I$(LIBNDS)/include -I$(CURDIR)/build
export LIBPATHS := -L$(LIBNDS)/lib
export LD := $(CC)
.PHONY: $(BUILD) clean
$(BUILD):
	@mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
clean:
	rm -rf build $(TARGET).nds $(TARGET).elf
else
$(OUTPUT).nds : $(OUTPUT).elf
$(OUTPUT).elf : $(OFILES)
-include $(DEPSDIR)/*.d
endif
"""
    return {"src/main.c":code,"Makefile":make}

def psp_source(seed:int)->dict[str,str]:
    seed=_seed(seed)
    code=r'''/* Original native PSP homebrew: PSPSDK HUD, analog and button play. */
#include <pspkernel.h>
#include <pspdebug.h>
#include <pspctrl.h>
#include <pspdisplay.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
PSP_MODULE_INFO("Dragon PSP Quest",0,1,0);
PSP_MAIN_THREAD_ATTR(THREAD_ATTR_USER);
static int x=5,y=6,star_x=__STARX__,star_y=__STARY__;
static int foe_x=39,foe_y=19,hp=5,score=0,stage=1,frames=0,damaged=0;
static uint32_t rng=__SEED__u;
static uint32_t rnd(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void reset(void){
 x=5;y=6;star_x=__STARX__;star_y=__STARY__;
 foe_x=39;foe_y=19;hp=5;score=0;stage=1;damaged=0;frames=0;
 rng=__SEED__u;
}
static void field(void){
 pspDebugScreenSetXY(0,0);
 pspDebugScreenPrintf("DRAGON PSP 3D-ERA HOMEBREW\\n");
 pspDebugScreenPrintf("Crystals:%d Level:%d HP:%d\\n",score,stage,hp);
 pspDebugScreenPrintf("Analog/D-pad move | START reset\\n");
 for(int row=0;row<25;row++){
  pspDebugScreenSetXY(0,row+4);
  for(int col=0;col<57;col++){
   char tile=' ';
   if(row==0||row==24||col==0||col==56)tile='#';
   else if(col==star_x&&row==star_y)tile='*';
   else if(col==foe_x&&row==foe_y)tile='X';
   else if(col==x&&row==y)tile='D';
   pspDebugScreenPrintf("%c",tile);
  }
 }
 if(hp<=0){
  pspDebugScreenSetXY(12,18);
  pspDebugScreenPrintf("HATCHLING DOWN - X RETRY");
 }
}
int main(void){
 pspDebugScreenInit();
 sceCtrlSetSamplingCycle(0);
 sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);
 reset();
 SceCtrlData pad;
 while(1){
  sceCtrlPeekBufferPositive(&pad,1);
  if(pad.Buttons&PSP_CTRL_START)reset();
  if(hp>0){
   if((pad.Buttons&PSP_CTRL_LEFT)||pad.Lx<80)x--;
   if((pad.Buttons&PSP_CTRL_RIGHT)||pad.Lx>176)x++;
   if((pad.Buttons&PSP_CTRL_UP)||pad.Ly<80)y--;
   if((pad.Buttons&PSP_CTRL_DOWN)||pad.Ly>176)y++;
   if(x<1)x=1;if(x>55)x=55;
   if(y<1)y=1;if(y>23)y=23;
   if(x==star_x&&y==star_y){
    score++;stage=1+score/4;star_x=2+rnd()%53;
    star_y=2+rnd()%21;if(score%5==0&&hp<5)hp++;
   }
   if((frames%(8-(stage<6?stage:6)))==0){
    foe_x+=(x>foe_x)?1:-1;foe_y+=(y>foe_y)?1:-1;
   }
   if(damaged)damaged--;
   if(abs(foe_x-x)<2&&abs(foe_y-y)<2&&!damaged){
    hp--;damaged=40;
   }
  }else if(pad.Buttons&PSP_CTRL_CROSS)reset();
  if(frames%3==0){pspDebugScreenClear();field();}
  frames++;
  sceDisplayWaitVblankStart();
 }
 sceKernelExitGame();
 return 0;
}
'''
    code=(code.replace("__SEED__",str(seed or 1))
              .replace("__STARX__",str(10+seed%30))
              .replace("__STARY__",str(7+(seed//13)%12)))
    make="""\
TARGET = dragon_psp
OBJS = main.o
CFLAGS = -O2 -G0 -Wall
CXXFLAGS = $(CFLAGS)
ASFLAGS = $(CFLAGS)
LIBS = -lpspdebug -lpspctrl -lpspdisplay -lpspkernel
EXTRA_TARGETS = EBOOT.PBP
PSP_EBOOT_TITLE = Dragon Original PSP Quest
PSPSDK := $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak
main.o: src/main.c
\tpsp-gcc $(CFLAGS) -c $< -o $@
"""
    return {"src/main.c":code,"Makefile":make}
