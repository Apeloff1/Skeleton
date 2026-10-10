"""Original Nintendo Switch/libnx and Wii U/wut homebrew game projects.

Both games share a portable, independently host-testable deterministic C99
game core, but have real, distinct native graphics/input and SDK linkage.
This is original source only; proprietary firmware, vendor SDK and games
are not bundled. A host core selftest does not prove console execution.
"""
from __future__ import annotations

CORE_H=r'''#ifndef DRAGON_ORIGINAL_DUALSCREEN_H
#define DRAGON_ORIGINAL_DUALSCREEN_H
#include <stdint.h>
enum {DRAGON_W=18,DRAGON_H=12,DRAGON_STAGES=4,DRAGON_GEMS=3};
enum {DRAGON_PLAY=0,DRAGON_LOST=1,DRAGON_WON=2};
typedef struct {
 int x,y,hp,energy,score,stage,ticks,status;
 int collected[DRAGON_GEMS];
 int enemies[2][2];
 int invulnerability;
 uint32_t rng;
} DragonGame;
void dragon_reset(DragonGame *g,uint32_t seed);
void dragon_step(DragonGame *g,int dx,int dy,int attack,int restart);
int dragon_solid(int x,int y,int stage);
char dragon_tile(const DragonGame *g,int x,int y);
int dragon_selftest(void);
#endif
'''

CORE_C=r'''/* Original bounded 18x12, four-chapter collectible/chase game core.
   No SDK or display dependency; compiled and replayed on a native host. */
#include "dragon_game.h"
#include <string.h>
#define DRAGON_SEED __SEED__u
static uint32_t step_rng(DragonGame *g){
 uint32_t r=g->rng;
 r^=r<<13;r^=r>>17;r^=r<<5;
 return g->rng=r?r:0x9e3779b9u;
}
static int clamp(int x,int low,int high){
 return x<low?low:(x>high?high:x);
}
int dragon_solid(int x,int y,int stage){
 if(x<=0||x>=DRAGON_W-1||y<=0||y>=DRAGON_H-1)return 1;
 /* Low obstacle bands do not block the verified collectible corridor. */
 if(y>=4&&y<=8 && x==5+(stage&1)*2 && y!=6)return 1;
 if(y>=5&&y<=9 && x==12-(stage&1) && y!=7)return 1;
 return 0;
}
static void start_stage(DragonGame*g){
 g->x=2;g->y=2;
 for(int i=0;i<DRAGON_GEMS;i++)g->collected[i]=0;
 g->enemies[0][0]=14;g->enemies[0][1]=8;
 g->enemies[1][0]=15;g->enemies[1][1]=9;
 g->invulnerability=20;
}
void dragon_reset(DragonGame*g,uint32_t seed){
 memset(g,0,sizeof(*g));
 g->rng=seed?seed:0x1f15d00du;
 g->hp=5;g->energy=8;g->status=DRAGON_PLAY;
 start_stage(g);
}
static int gems_gathered(const DragonGame*g){
 int n=0;
 for(int i=0;i<DRAGON_GEMS;i++)n+=g->collected[i]?1:0;
 return n;
}
static void enemy_tick(DragonGame*g,int index){
 int*e=g->enemies[index];
 int direction=(step_rng(g)&1)?1:-1;
 int dx=(g->x>e[0])?1:(g->x<e[0]?-1:0);
 int dy=(g->y>e[1])?1:(g->y<e[1]?-1:0);
 int next_x=e[0]+(direction>0?dx:0);
 int next_y=e[1]+(direction<0?dy:0);
 if(!dragon_solid(next_x,next_y,g->stage)){e[0]=next_x;e[1]=next_y;}
}
void dragon_step(DragonGame*g,int dx,int dy,int attack,int restart){
 if(!g)return;
 if(restart){uint32_t saved=g->rng;dragon_reset(g,saved);return;}
 if(g->status!=DRAGON_PLAY)return;
 dx=clamp(dx,-1,1);dy=clamp(dy,-1,1);
 /* One axis per step: prevents diagonal wall tunneling. */
 if(dx && dy)dy=0;
 int nx=g->x+dx,ny=g->y+dy;
 if(!dragon_solid(nx,ny,g->stage)){g->x=nx;g->y=ny;}
 g->ticks++;
 if(g->invulnerability)g->invulnerability--;
 for(int i=0;i<DRAGON_GEMS;i++){
  if(!g->collected[i]&&g->x==4+2*i&&g->y==2){
   g->collected[i]=1;g->score+=100+25*g->stage;
   g->energy=clamp(g->energy+1,0,10);
  }
 }
 if(attack&&g->energy>=2){
  g->energy-=2;
  for(int i=0;i<2;i++){
   int ex=g->enemies[i][0],ey=g->enemies[i][1];
   if(ey==g->y && ex>g->x && ex-g->x<=4){
    g->score+=30;g->enemies[i][0]=14+i;
    g->enemies[i][1]=8+i;
   }
  }
 }
 if(g->ticks%8==0){
  for(int i=0;i<2;i++)enemy_tick(g,i);
 }
 if(!g->invulnerability){
  for(int i=0;i<2;i++){
   int dx2=g->x-g->enemies[i][0],dy2=g->y-g->enemies[i][1];
   if(dx2==0&&dy2==0){
    g->hp--;g->invulnerability=35;
    if(g->hp<=0){g->hp=0;g->status=DRAGON_LOST;}
    break;
   }
  }
 }
 if(g->status==DRAGON_PLAY &&
    g->x==10 && g->y==2 && gems_gathered(g)==DRAGON_GEMS){
  g->score+=250;
  if(++g->stage==DRAGON_STAGES){g->status=DRAGON_WON;return;}
  g->hp=clamp(g->hp+1,0,5);start_stage(g);
 }
}
char dragon_tile(const DragonGame*g,int x,int y){
 if(dragon_solid(x,y,g->stage))return '#';
 if(g->x==x&&g->y==y)return 'D';
 for(int i=0;i<2;i++)
  if(x==g->enemies[i][0]&&y==g->enemies[i][1])return 'X';
 for(int i=0;i<DRAGON_GEMS;i++)
  if(!g->collected[i]&&x==4+2*i&&y==2)return '*';
 if(x==10&&y==2)return 'O';
 return '.';
}
int dragon_selftest(void){
 DragonGame a,b;
 dragon_reset(&a,DRAGON_SEED);
 dragon_reset(&b,DRAGON_SEED);
 if(a.status!=DRAGON_PLAY||a.hp!=5)return 1;
 for(int stage=0;stage<DRAGON_STAGES;stage++){
  for(int move=0;move<8;move++){
   dragon_step(&a,1,0,0,0);dragon_step(&b,1,0,0,0);
   if(memcmp(&a,&b,sizeof(a)))return 2;
  }
  if(stage+1<DRAGON_STAGES && a.stage!=stage+1)return 3;
 }
 if(a.status!=DRAGON_WON || a.stage!=DRAGON_STAGES)return 4;
 if(a.score!=DRAGON_STAGES*(100*DRAGON_GEMS+25*DRAGON_GEMS*(DRAGON_STAGES-1)/2/DRAGON_STAGES+250)){
  /* Sum exact stage-specific rewards explicitly below for clarity. */
  if(a.score!=2350)return 5;
 }
 dragon_step(&a,1,0,0,0);
 if(a.status!=DRAGON_WON)return 6;
 dragon_reset(&a,DRAGON_SEED);
 if(a.hp!=5||a.score!=0||a.stage!=0)return 7;
 for(int y=0;y<DRAGON_H;y++)
  for(int x=0;x<DRAGON_W;x++)
   if(dragon_tile(&a,x,y)==0)return 8;
 return 0;
}
'''
# Score: stage n: 300+75*n+250 => 550,625,700,775 total 2650, not 2350
CORE_C=CORE_C.replace(' if(a.score!=DRAGON_STAGES*(100*DRAGON_GEMS+25*DRAGON_GEMS*(DRAGON_STAGES-1)/2/DRAGON_STAGES+250)){\n  /* Sum exact stage-specific rewards explicitly below for clarity. */\n  if(a.score!=2350)return 5;\n }',' if(a.score!=2650)return 5;')

SWITCH_MAIN=r'''/* Original libnx game, handheld and docked Npad input and native console. */
#include <switch.h>
#include <stdio.h>
#include <string.h>
#include "dragon_game.h"
#define SEED __SEED__u
static void show(const DragonGame*g){
 printf("\x1b[1;1H\x1b[2J");
 printf("  DRAGON: FOUR CRYSTAL CHAPTERS  (Switch Homebrew)\n");
 printf("  Chapter %d/%d  Score %d  HP %d  Energy %d\n",
   g->stage+1,DRAGON_STAGES,g->score,g->hp,g->energy);
 for(int y=0;y<DRAGON_H;y++){
  printf("  ");
  for(int x=0;x<DRAGON_W;x++)putchar(dragon_tile(g,x,y));
  putchar('\n');
 }
 if(g->status==DRAGON_LOST)puts("  GAME OVER - press X to restart.");
 else if(g->status==DRAGON_WON)puts("  FOUR CHAPTERS WON - press X to play again.");
 else puts("  Collect *** then reach O. Dodge X. A=attack, B=guard.");
 puts("  D-pad move, X reset, + exit.");
}
int main(int argc,char**argv){
 (void)argc;(void)argv;
 consoleInit(NULL);
 padConfigureInput(1,HidNpadStyleSet_NpadStandard);
 PadState pad;padInitializeDefault(&pad);
 DragonGame game;dragon_reset(&game,SEED);
 if(argc==2&&strcmp(argv[1],"--selftest")==0){
  int result=dragon_selftest();consoleExit(NULL);return result;
 }
 while(appletMainLoop()){
  padUpdate(&pad);
  u64 held=padGetButtons(&pad),down=padGetButtonsDown(&pad);
  if(down&HidNpadButton_Plus)break;
  int dx=!!(held&HidNpadButton_Right)-!!(held&HidNpadButton_Left);
  int dy=!!(held&HidNpadButton_Down)-!!(held&HidNpadButton_Up);
  int action=!!(down&HidNpadButton_A);
  int restart=!!(down&HidNpadButton_X);
  dragon_step(&game,dx,dy,action,restart);
  show(&game);
  consoleUpdate(NULL);
  svcSleepThread(16000000L);
 }
 consoleExit(NULL);
 return 0;
}
'''
# remove mention unused guard
SWITCH_MAIN=SWITCH_MAIN.replace('A=attack, B=guard.','A=attack.')
WIIU_MAIN=r'''/* Wii U: native wut GamePad VPAD, TV+DRC OSScreen, ProcUI lifecycle. */
#include <coreinit/cache.h>
#include <coreinit/screen.h>
#include <coreinit/thread.h>
#include <vpad/input.h>
#include <whb/proc.h>
#include <malloc.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "dragon_game.h"
#define SEED __SEED__u
static void render(VPADStatus*pad,const DragonGame*g){
 char line[96];
 OSScreenClearBufferEx(SCREEN_TV,0x12203600);
 OSScreenClearBufferEx(SCREEN_DRC,0x12203600);
 snprintf(line,sizeof(line),"DRAGON WII U - Chapter %d / %d",g->stage+1,DRAGON_STAGES);
 OSScreenPutFontEx(SCREEN_TV,2,1,line);
 OSScreenPutFontEx(SCREEN_DRC,1,1,line);
 snprintf(line,sizeof(line),"Crystals %d   HP %d   Energy %d",g->score,g->hp,g->energy);
 OSScreenPutFontEx(SCREEN_TV,2,3,line);
 OSScreenPutFontEx(SCREEN_DRC,1,3,line);
 for(int y=0;y<DRAGON_H;y++){
  for(int x=0;x<DRAGON_W;x++)line[x]=dragon_tile(g,x,y);
  line[DRAGON_W]=0;
  OSScreenPutFontEx(SCREEN_TV,2,y+5,line);
  OSScreenPutFontEx(SCREEN_DRC,1,y+5,line);
 }
 if(g->status==DRAGON_WON){
  OSScreenPutFontEx(SCREEN_TV,2,19,"ALL FOUR CHAPTERS WON - X restart");
  OSScreenPutFontEx(SCREEN_DRC,1,19,"GAME WON - X restart");
 }else if(g->status==DRAGON_LOST){
  OSScreenPutFontEx(SCREEN_TV,2,19,"GAME OVER - X restart");
  OSScreenPutFontEx(SCREEN_DRC,1,19,"GAME OVER - X restart");
 }else{
  OSScreenPutFontEx(SCREEN_TV,2,19,"D-PAD move / A attack / X restart");
  OSScreenPutFontEx(SCREEN_DRC,1,19,"Collect * then reach O, avoid X.");
 }
 (void)pad;
}
int main(void){
 if(!WHBProcInit())return 1;
 OSScreenInit();
 size_t tvSize=OSScreenGetBufferSizeEx(SCREEN_TV);
 size_t drcSize=OSScreenGetBufferSizeEx(SCREEN_DRC);
 void *tv=memalign(0x100,tvSize),*drc=memalign(0x100,drcSize);
 if(!tv||!drc){
  free(tv);free(drc);
  OSScreenShutdown();WHBProcShutdown();return 2;
 }
 OSScreenSetBufferEx(SCREEN_TV,tv);OSScreenSetBufferEx(SCREEN_DRC,drc);
 OSScreenEnableEx(SCREEN_TV,true);OSScreenEnableEx(SCREEN_DRC,true);
 DragonGame game;dragon_reset(&game,SEED);
 VPADStatus pad={0};VPADReadError error=VPAD_READ_NO_SAMPLES;
 int frame=0;
 while(WHBProcIsRunning()){
  VPADRead(VPAD_CHAN_0,&pad,1,&error);
  if(error==VPAD_READ_INVALID_CONTROLLER)break;
  if(error==VPAD_READ_SUCCESS){
   int dx=!!(pad.hold&VPAD_BUTTON_RIGHT)-!!(pad.hold&VPAD_BUTTON_LEFT);
   int dy=!!(pad.hold&VPAD_BUTTON_DOWN)-!!(pad.hold&VPAD_BUTTON_UP);
   dragon_step(&game,dx,dy,!!(pad.trigger&VPAD_BUTTON_A),
               !!(pad.trigger&VPAD_BUTTON_X));
  }
  if((++frame&1)==0){
   render(&pad,&game);
   DCFlushRange(tv,tvSize);DCFlushRange(drc,drcSize);
   OSScreenFlipBuffersEx(SCREEN_TV);OSScreenFlipBuffersEx(SCREEN_DRC);
  }
  OSSleepTicks(OSMillisecondsToTicks(16));
 }
 OSScreenShutdown();free(tv);free(drc);WHBProcShutdown();
 return 0;
}
'''
SWITCH_MAKE=r'''# Native Nintendo Switch homebrew, not a renamed desktop executable.
ifeq ($(strip $(DEVKITPRO)),)
$(error DEVKITPRO required; install switch-dev)
endif
include $(DEVKITPRO)/libnx/switch_rules
TARGET := dragon_original
BUILD := build
SOURCES := source
INCLUDES := source
ARCH := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
CFLAGS := -O2 -std=c99 -Wall -Wextra -ffunction-sections $(ARCH) -D__SWITCH__
CFLAGS += $(INCLUDE)
LDFLAGS := -specs=$(DEVKITPRO)/libnx/switch.specs $(ARCH)
LIBS := -lnx
LIBDIRS := $(DEVKITPRO)/libnx
ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT := $(CURDIR)/$(TARGET)
export TOPDIR := $(CURDIR)
export VPATH := $(CURDIR)/source
export DEPSDIR := $(CURDIR)/$(BUILD)
export OFILES := main.o dragon_game.o
export INCLUDE := -I$(CURDIR)/source -I$(DEVKITPRO)/libnx/include -I$(CURDIR)/$(BUILD)
export LIBPATHS := -L$(DEVKITPRO)/libnx/lib
export LD := $(CC)
.PHONY: all clean $(BUILD)
all: $(BUILD)
$(BUILD):
	@mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
clean:
	rm -rf $(BUILD) $(TARGET).elf $(TARGET).nro $(TARGET).nacp
else
all: $(OUTPUT).nro
$(OUTPUT).nro: $(OUTPUT).elf $(OUTPUT).nacp
$(OUTPUT).elf: $(OFILES)
-include $(OFILES:.o=.d)
endif
'''
WIIU_CMAKE=r'''cmake_minimum_required(VERSION 3.13)
project(dragon_original C)
add_executable(dragon_original src/main.c src/dragon_game.c)
target_include_directories(dragon_original PRIVATE src)
# devkitPro wut CMake toolchain injects wut_create_rpx.
if(NOT COMMAND wut_create_rpx)
  message(FATAL_ERROR "Native Wii U wut CMake toolchain is required")
endif()
wut_create_rpx(dragon_original)
'''
def original_nintendo_source(target_id:str,seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("native seed must be uint32")
    seed=seed or 1
    if target_id=="nintendo_switch":
        return {
            "source/main.c":SWITCH_MAIN.replace("__SEED__",str(seed)),
            "source/dragon_game.c":CORE_C.replace("__SEED__",str(seed)),
            "source/dragon_game.h":CORE_H,
            "Makefile":SWITCH_MAKE,
            "README.port.md":(
              "# Original Switch libnx homebrew source\n\n"
              "Use an independently installed, lawful devkitA64/libnx switch-dev "
              "environment, then run make to produce a real NRO. Supports Joy-Con,"
              " handheld/docked D-pad, native console drawing and four independently "
              "scripted original chapters. A host C99 source replay is included as "
              "a separate quality gate. No NRO, firmware or copyrighted assets bundled."
              " Device, audio and controller certification remain unverified.\n"),
        }
    if target_id=="wii_u":
        return {
            "src/main.c":WIIU_MAIN.replace("__SEED__",str(seed)),
            "src/dragon_game.c":CORE_C.replace("__SEED__",str(seed)),
            "src/dragon_game.h":CORE_H,
            "CMakeLists.txt":WIIU_CMAKE,
            "README.port.md":(
              "# Original Wii U wut RPX homebrew source\n\n"
              "Use the public devkitPro wiiu-dev/wut toolchain and its "
              "powerpc-eabi-cmake wrapper. VPAD GamePad D-pad/action controls; "
              "real OSScreen television and Wii U controller displays, "
              "four original deterministic chapters with crystals and enemies."
              " This generates an RPX SDK source project, NOT a packaged WUHB. "
              " Emulation, audio/video timing, physical controls and legal "
              " distribution authorization are not claimed.\n"),
        }
    raise ValueError("unknown open Nintendo homebrew target")
