"""Distinct original Jo Engine Saturn and VitaSDK Vita game emitters."""
from __future__ import annotations

SATURN_C=r'''/* Original Sega Saturn Jo Engine game. Native pad and VDP2 text.
   No vendor ROM/assets, SDK auth keys, PlayStation emulator or HTML. */
#include <jo/jo.h>
static int x=8,y=10,starx=28,stary=12,fx=35,fy=19;
static int score=0,hp=5,level=1,frame=0,shield=0,won=0;
static unsigned int rng=__SEED__u;
static unsigned int next_rng(void){
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void){
 rng=__SEED__u;x=8;y=10;starx=28;stary=12;fx=35;fy=19;
 score=0;hp=5;level=1;frame=0;shield=0;won=0;
}
static void update(void){
 if(jo_is_pad1_key_pressed(JO_KEY_START)){reset();return;}
 if(!hp||won)return;
 x+=(jo_is_pad1_key_down(JO_KEY_RIGHT)?1:0)
   -(jo_is_pad1_key_down(JO_KEY_LEFT)?1:0);
 y+=(jo_is_pad1_key_down(JO_KEY_DOWN)?1:0)
   -(jo_is_pad1_key_down(JO_KEY_UP)?1:0);
 if(x<1)x=1;if(x>39)x=39;
 if(y<4)y=4;if(y>25)y=25;
 if(x==starx&&y==stary){
  score++;level=1+score/4;
  starx=(int)(2+next_rng()%36);stary=(int)(5+next_rng()%20);
  if(score%5==0&&hp<5)hp++;
  if(score>=18)won=1;
 }
 frame++;
 if(shield)shield--;
 if(frame%(13-(level>8?8:level))==0){
  fx+=(x>fx?1:-1);fy+=(y>fy?1:-1);
 }
 if(x==fx&&y==fy&&!shield){hp--;shield=45;fx=36;fy=23;}
}
static void render(void){
 jo_clear_screen();
 jo_printf(1,1,"ORIGINAL DRAGON SATURN");
 jo_printf(1,2,"STARS %d / 18    HP %d",score,hp);
 jo_printf(1,3,"D-PAD MOVE  START RESTART");
 jo_printf(starx,stary,"*");
 jo_printf(fx,fy,"X");
 jo_printf(x,y,"D");
 if(won)jo_printf(7,18,"ORIGINAL QUEST COMPLETE");
 else if(!hp)jo_printf(7,18,"DRAGON DOWN");
}
static void frame_update(void){update();render();}
void jo_main(void){
 reset();
 jo_core_init(JO_COLOR_Black);
 jo_core_add_callback(frame_update);
 jo_core_run();
}
'''
SATURN_MAKE="""\
# Based on the MIT Jo Engine official sample build interface.
# Set JO_ENGINE_ROOT to the external public Jo Engine checkout.
ifndef JO_ENGINE_ROOT
$(error Set JO_ENGINE_ROOT to an installed Jo Engine source checkout)
endif
JO_COMPILE_WITH_VIDEO_MODULE = 0
JO_COMPILE_WITH_BACKUP_MODULE = 0
JO_COMPILE_WITH_TGA_MODULE = 0
JO_COMPILE_WITH_AUDIO_MODULE = 0
JO_COMPILE_WITH_3D_MODULE = 0
JO_COMPILE_WITH_EFFECTS_MODULE = 0
JO_COMPILE_USING_SGL = 1
JO_COMPILE_WITH_PRINTF_SUPPORT = 1
JO_DEBUG = 0
JO_NTSC = 1
SRCS = src/main.c
JO_ENGINE_SRC_DIR = $(JO_ENGINE_ROOT)/jo_engine
COMPILER_DIR = $(JO_ENGINE_ROOT)/Compiler
include $(COMPILER_DIR)/COMMON/jo_engine_makefile
"""
VITA_C=r'''/* Original Vita handheld RPG-like survival game.
   VitaSDK userland native GPU via vita2d, SceCtrl and front touch.
   No DRM bypass, firmware files, imported game assets or proprietary SDK. */
#include <psp2/ctrl.h>
#include <psp2/touch.h>
#include <psp2/kernel/processmgr.h>
#include <vita2d.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define FOES 5
static int x,y,gemx,gemy,hp,score,level,shield,won,tick;
static int enemy_x[FOES],enemy_y[FOES];
static uint32_t rng=__SEED__u;
static uint32_t next_rng(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void reset(void){
 rng=__SEED__u;x=80;y=220;gemx=620;gemy=300;
 hp=5;score=0;level=1;shield=0;won=0;tick=0;
 for(int i=0;i<FOES;i++){enemy_x[i]=770-i*49;enemy_y[i]=70+i*81;}
}
static int near(int ax,int ay,int bx,int by,int r){
 return abs(ax-bx)<r&&abs(ay-by)<r;
}
static void advance(const SceCtrlData*pad,const SceTouchData*touch){
 if(pad->buttons&SCE_CTRL_START){reset();return;}
 if(won||!hp)return;
 int dx=3*((pad->buttons&SCE_CTRL_RIGHT)!=0)-
         3*((pad->buttons&SCE_CTRL_LEFT)!=0);
 int dy=3*((pad->buttons&SCE_CTRL_DOWN)!=0)-
         3*((pad->buttons&SCE_CTRL_UP)!=0);
 if(pad->lx<80)dx-=2;else if(pad->lx>176)dx+=2;
 if(pad->ly<80)dy-=2;else if(pad->ly>176)dy+=2;
 x+=dx;y+=dy;
 if(x<8)x=8;if(x>922)x=922;
 if(y<23)y=23;if(y>506)y=506;
 int get=near(x,y,gemx,gemy,28);
 if(touch->reportNum>0){
  /* Vita front-touch max coordinates differ by runtime mode. The
     2:1 mapping requires physical-device scale confirmation. */
  int tx=touch->report[0].x/2,ty=touch->report[0].y/2;
  if(near(tx,ty,gemx,gemy,32))get=1;
 }
 if(get){
  score++;level=1+score/4;
  gemx=35+(int)(next_rng()%880);gemy=50+(int)(next_rng()%440);
  if(score%5==0&&hp<5)hp++;
  if(score>=25)won=1;
 }
 tick++;
 if(shield)shield--;
 for(int i=0;i<FOES;i++){
  if(tick%(12+i*3-(level>8?8:level))==0){
   enemy_x[i]+=(x>enemy_x[i]?2:-2);
   enemy_y[i]+=(y>enemy_y[i]?2:-2);
  }
  if(near(x,y,enemy_x[i],enemy_y[i],25)&&!shield){
   hp--;shield=60;enemy_x[i]=760+i*25;enemy_y[i]=70+i*79;
  }
 }
}
static void render(void){
 vita2d_start_drawing();
 vita2d_clear_screen();
 for(int i=0;i<12;i++)
  vita2d_draw_rectangle(i*80,22,1,500,RGBA8(31,51,73,255));
 for(int i=0;i<hp;i++)
  vita2d_draw_rectangle(12+i*32,9,22,11,RGBA8(243,88,113,255));
 vita2d_draw_rectangle(gemx,gemy,20,20,RGBA8(255,216,109,255));
 vita2d_draw_rectangle(gemx+6,gemy+4,7,8,RGBA8(255,246,183,255));
 if(!shield||tick%8<4){
  vita2d_draw_rectangle(x,y,30,30,RGBA8(86,227,157,255));
  vita2d_draw_rectangle(x+20,y+8,6,6,RGBA8(19,44,48,255));
 }
 for(int i=0;i<FOES;i++)
  vita2d_draw_rectangle(enemy_x[i],enemy_y[i],24,24,RGBA8(224,75,104,255));
 for(int i=0;i<score&&i<27;i++)
  vita2d_draw_rectangle(10+i*29,525,18,9,RGBA8(246,213,94,255));
 if(won||!hp)
  vita2d_draw_rectangle(300,215,360,100,won?
    RGBA8(37,164,105,255):RGBA8(154,40,73,255));
 vita2d_end_drawing();vita2d_swap_buffers();
}
int main(void){
 SceCtrlData pad;SceTouchData touch;
 vita2d_init();
 vita2d_set_clear_color(RGBA8(13,23,44,255));
 sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
 sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT,SCE_TOUCH_SAMPLING_STATE_START);
 reset();
 for(;;){
  memset(&pad,0,sizeof(pad));memset(&touch,0,sizeof(touch));
  sceCtrlPeekBufferPositive(0,&pad,1);
  sceTouchPeek(SCE_TOUCH_PORT_FRONT,&touch,1);
  if(pad.buttons&SCE_CTRL_SELECT)break;
  advance(&pad,&touch);render();
 }
 vita2d_fini();sceKernelExitProcess(0);
 return 0;
}
'''
VITA_CMAKE="""\
cmake_minimum_required(VERSION 3.16)
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake"
        CACHE PATH "VitaSDK toolchain")
  else()
    message(FATAL_ERROR "VITASDK is needed for native Vita homebrew")
  endif()
endif()
project(OriginalDragonVita C)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
set(CMAKE_C_STANDARD 99)
add_executable(dragon_vita src/main.c)
target_compile_options(dragon_vita PRIVATE -O2 -Wall -Wextra -fno-lto)
target_link_libraries(dragon_vita vita2d
 SceCtrl_stub SceTouch_stub SceDisplay_stub SceGxm_stub
 SceSysmodule_stub SceAppMgr_stub ScePgf_stub ScePvf_stub
 freetype png jpeg z m)
vita_create_self(eboot.bin dragon_vita SAFE)
vita_create_vpk(dragon_vita.vpk DRGN00001 eboot.bin
 VERSION 01.00 NAME "Original Dragon Vita")
"""
def _validated(seed:int)->int:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("native console game seed must be uint32")
    return seed or 1
def saturn_source(seed:int)->dict[str,str]:
    seed=_validated(seed)
    return {"src/main.c":SATURN_C.replace("__SEED__",str(seed)),
            "Makefile":SATURN_MAKE,
            "README.port.md":(
             "# Original Sega Saturn Jo Engine\n\n"
             "Original Saturn pad+VDP2 native Jo Engine source and installed "
             "public Jo Engine build configuration. Compile only with an "
             "independently installed Jo Engine+SH2 toolchain and ISO packager. "
             "No Sega proprietary SDK, copied assets or compiled CD image. "
             "Live controller and emulator testing remains unverified.\n")}
def vita_source(seed:int)->dict[str,str]:
    seed=_validated(seed)
    return {"src/main.c":VITA_C.replace("__SEED__",str(seed)),
            "CMakeLists.txt":VITA_CMAKE,
            "README.port.md":(
             "# Original PS Vita VitaSDK C game\n\n"
             "Standalone VitaSDK homebrew using real SceCtrl, front touch, "
             "vita2d framebuffer/GPU, five chasing enemies, collecting, "
             "lives, restart and 25-item victory. VPK source project "
             "requires installed VitaSDK/libvita2d and exact target build. "
             "No copied Sony assets, firmware, games or keys included; "
             "emulator and physical controls are still unverified.\n")}
