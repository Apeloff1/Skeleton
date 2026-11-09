"""Native SNES LoROM original arcade quest using PVSnesLib 65816 runtime.

This is a real Super Nintendo program using the SNES text tile background,
automatic joypad read and vertical blank timing, NOT a PC/browser port.
Full PVSnesLib installed separately provides fonts, linker and SNES startup.
"""
from __future__ import annotations

def snes_source(seed:int)->dict[str,str]:
    if isinstance(seed,bool) or not isinstance(seed,int) or seed<0:
        raise ValueError("invalid SNES game seed")
    target_x=8+seed%18
    target_y=6+(seed//11)%14
    enemy_x=14+(seed//47)%10
    source=r'''/* Original SNES/65816 homebrew. PVSnesLib background tile console.
 * Native joypad, vblank, encounters, stage transitions and lives.
 * SDK fonts and startup are provided by user-installed PVSnesLib.
 */
#include <snes.h>
#include <stdint.h>
static s16 x=5,y=6;
static s16 gem_x=__GEM_X__,gem_y=__GEM_Y__;
static s16 foe_x=__FOE_X__,foe_y=16;
static u16 stage=1,score=0,lives=4,frame=0;
static u16 halted=0,enemy_cooldown=0;
static void floor_tiles(void){
  u16 i;
  consoleDrawText(5,1,"DRAGON SNES NATIVE QUEST");
  consoleDrawText(4,2,"D-PAD MOVE AVOID FOE");
  consoleDrawText(2,4,"----------------------------");
  consoleDrawText(2,25,"----------------------------");
  for(i=5;i<25;i++){
    consoleDrawText(2,i,"|");
    consoleDrawText(29,i,"|");
  }
}
static void status(void){
  consoleDrawText(3,26,"CRYSTALS:%d  STAGE:%d  HP:%d ",score,stage,lives);
}
static void new_stage(void){
  stage++;
  score+=(u16)(stage*15u);
  gem_x=(s16)(5+(stage*7u+__SEED_X__)%21u);
  gem_y=(s16)(6+(stage*5u+__SEED_Y__)%17u);
  foe_x=(s16)(5+(stage*11u+__SEED_X__)%21u);
  foe_y=14;
  x=4;y=6;
  lives=(u16)(lives<4?lives+1:lives);
  floor_tiles();
  status();
}
static void reset(void){
  x=4;y=6;score=0;stage=1;lives=4;
  gem_x=__GEM_X__;gem_y=__GEM_Y__;
  foe_x=__FOE_X__;foe_y=16;
  frame=0;halted=0;enemy_cooldown=0;
  floor_tiles();
  status();
}
int main(void){
  u16 pad;
  /* PVSnesLib sets SNES tile font and mode 1 graphics hardware. */
  consoleInitDefaultText(0);
  bgSetGfxPtr(0,0x3000);
  bgSetMapPtr(0,0x6800,SC_32x32);
  setMode(BG_MODE1,0);
  bgSetDisable(1);
  bgSetDisable(2);
  reset();
  setScreenOn();
  while(1){
    pad=padsCurrent(0);
    if(pad&KEY_START){reset();}
    if(!halted&&(frame%3u)==0u){
      s16 oldx=x,oldy=y;
      if((pad&KEY_LEFT)&&x>3)x--;
      if((pad&KEY_RIGHT)&&x<28)x++;
      if((pad&KEY_UP)&&y>5)y--;
      if((pad&KEY_DOWN)&&y<24)y++;
      if(oldx!=x||oldy!=y)consoleDrawText(oldx,oldy," ");
      if((frame%12u)==0u){
        consoleDrawText(foe_x,foe_y," ");
        if((frame/12u)%2u==0u){if(foe_x<27)foe_x++;}
        else if(foe_x>4)foe_x--;
      }
      if(x==gem_x&&y==gem_y){
        consoleDrawText(gem_x,gem_y," ");
        new_stage();
      }
      if(enemy_cooldown>0)enemy_cooldown--;
      if(x==foe_x&&y==foe_y&&!enemy_cooldown){
        if(lives>0)lives--;
        enemy_cooldown=30;
        x=4;y=6;status();
        if(lives==0){
          halted=1;
          consoleDrawText(8,13,"HATCHLING DOWN");
          consoleDrawText(7,14,"START TO REPLAY");
        }
      }
      status();
    }
    if(!halted){
      consoleDrawText(gem_x,gem_y,"*");
      consoleDrawText(foe_x,foe_y,"X");
      consoleDrawText(x,y,"@");
    }
    frame++;
    WaitForVBlank();
  }
  return 0;
}
'''
    source=(source.replace("__GEM_X__",str(target_x))
                  .replace("__GEM_Y__",str(target_y))
                  .replace("__FOE_X__",str(enemy_x))
                  .replace("__SEED_X__",str(seed%97))
                  .replace("__SEED_Y__",str((seed//17)%89)))
    make="""\
ifndef PVSNESLIB_HOME
$(error Install official PVSnesLib and set PVSNESLIB_HOME)
endif
export ROMNAME := dragon_snes
export ROMTITLE := DRAGON ORIGINAL QUEST
export ROMSIZE := 08
export SRAMSIZE := 00
export COUNTRY := 01
SRC := ./src
include $(PVSNESLIB_HOME)/devkitsnes/snes_rules
"""
    return {"src/main.c":source,"Makefile":make}
