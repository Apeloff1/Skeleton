"""Native Playdate C game generator, with real crank/D-pad input."""
from __future__ import annotations
SRC=r'''#include "pd_api.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
/* Original Dragon Crank collector, 400x240 monochrome, 30 FPS. */
static PlaydateAPI *api;
static uint32_t rng=__SEED__u;
static int x,y,gemx,gemy,foex,foey,hp,score,level,invuln,energy,frame;
static uint32_t rnd(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void restart(void){
 rng=__SEED__u;x=40;y=80;gemx=250;gemy=120;foex=340;foey=175;
 hp=4;score=0;level=1;invuln=0;energy=0;frame=0;
}
static int close_to(int a,int b,int c,int d){
 return a<c+17&&a+17>c&&b<d+17&&b+17>d;
}
static int update(void *ud){
 (void)ud;
 PDButtons held=0,pressed=0;
 api->system->getButtonState(&held,&pressed,0);
 if(pressed&kButtonB)restart();
 if(hp){
  int speed=(held&kButtonA)&&energy>0?5:3;
  if(speed==5)energy--;
  if(held&kButtonLeft)x-=speed;if(held&kButtonRight)x+=speed;
  if(held&kButtonUp)y-=speed;if(held&kButtonDown)y+=speed;
  if(x<8)x=8;if(x>371)x=371;
  if(y<28)y=28;if(y>212)y=212;
  float c=api->system->getCrankChange();
  if(c>4||c< -4){energy+=(int)((c<0?-c:c)/2);if(energy>100)energy=100;}
  if(close_to(x,y,gemx,gemy)){
   score++;level=1+score/5;
   gemx=18+(int)(rnd()%349);gemy=30+(int)(rnd()%170);
  }
  if(invuln)invuln--;
  if(frame%(12-(level>7?7:level))==0){
   foex+=x>foex?2:-2;foey+=y>foey?2:-2;
  }
  if(!invuln&&close_to(x,y,foex,foey)){
   hp--;invuln=35;foex=340;foey=175;
  }
 }
 frame++;
 api->graphics->clear(kColorWhite);
 char hud[72];
 snprintf(hud,sizeof(hud),"DRAGON CRANK  SCORE %03d L%d HP%d",score,level,hp);
 api->graphics->drawText(hud,strlen(hud),kASCIIEncoding,6,6);
 api->graphics->drawRect(6,28,386,202,kColorBlack);
 api->graphics->fillRect(gemx,gemy,13,13,kColorBlack);
 api->graphics->fillRect(gemx+4,gemy+4,5,5,kColorWhite);
 api->graphics->fillRect(foex,foey,17,17,kColorBlack);
 if(!invuln||(frame&2)){
  api->graphics->fillRect(x,y,17,17,kColorBlack);
  api->graphics->fillRect(x+12,y+3,3,3,kColorWhite);
 }
 api->graphics->fillRect(288,235,energy,4,kColorBlack);
 if(!hp)api->graphics->drawText("B TO RESTART",12,kASCIIEncoding,110,115);
 return 1;
}
#ifdef _WINDLL
__declspec(dllexport)
#endif
int eventHandler(PlaydateAPI* pd,PDSystemEvent event,uint32_t arg){
 (void)arg;
 if(event==kEventInit){
  api=pd;restart();api->display->setRefreshRate(30);
  api->system->setUpdateCallback(update,0);
 }
 return 0;
}
'''
CMAKE=r'''cmake_minimum_required(VERSION 3.14)
set(CMAKE_C_STANDARD 11)
if(NOT DEFINED ENV{PLAYDATE_SDK_PATH})
 message(FATAL_ERROR "Playdate SDK required")
endif()
set(PLAYDATE_GAME_NAME DragonCrank)
set(PLAYDATE_GAME_DEVICE DragonCrank_DEVICE)
project(DragonCrank C ASM)
if(TOOLCHAIN STREQUAL "armgcc")
 add_executable(DragonCrank_DEVICE "$ENV{PLAYDATE_SDK_PATH}/C_API/buildsupport/setup.c" src/main.c)
else()
 add_library(DragonCrank SHARED src/main.c)
endif()
include("$ENV{PLAYDATE_SDK_PATH}/C_API/buildsupport/playdate_game.cmake")
'''
def playdate_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Playdate seed must be uint32")
    return {
      "src/main.c":SRC.replace("__SEED__",str(seed or 1)),
      "CMakeLists.txt":CMAKE,
      "Source/pdxinfo":"name=Dragon Crank Quest\n"
        "author=Original Homebrew\n"
        "description=Original Playdate one-bit action\n"
        "bundleID=com.originalhomebrew.dragoncrank\nversion=1.0.0\n",
      "README.port.md":"Playdate C SDK native source, not packaged. "
        "Crank charges dash; D-pad moves, A dashes, B restarts. "
        "Requires lawful SDK installed, cmake -S . -B build and native "
        "arm.cmake for device. SDK, simulator and hardware checks pending.\n",
    }
