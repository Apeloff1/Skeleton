"""Original Sega Master System and Game Gear ROM game source with devkitSMS.

Both use Z80, SMSlib, native VDP/CRAM, controller status and 8x8 hardware
sprites. Game Gear uses TARGET_GG 12-bit palette and 160x144 constraints;
SMS uses 6-bit palette and 256x192 constraints. SDCC and devkitSMS are
external prerequisites. This module does not claim an executable ROM exists.
"""
from __future__ import annotations
from .dragon_retro_assets import BITMAPS

def _sms_tile(name:str)->str:
    pixels=BITMAPS[name]
    packed=[]
    for row in pixels:
        planes=[0,0,0,0]
        for x,digit in enumerate(row):
            n=int(digit)
            for plane in range(4):
                planes[plane]|=((n>>plane)&1) << (7-x)
        packed.extend(planes)
    return "    "+", ".join("0x%02X"%p for p in packed)

def sms_source(seed:int,*,game_gear:bool=False)->dict[str,str]:
    if not isinstance(seed,int) or seed<0:raise ValueError("invalid native source seed")
    max_x=149 if game_gear else 247
    max_y=132 if game_gear else 184
    goal_x=70+seed%(max_x-72)
    goal_y=48+(seed//11)%(max_y-52)
    source=r'''/* Original Z80 native Sega homebrew. devkitSMS/SMSlib and SDCC.
   16-color VDP tile sprites, CRAM palettes, SMS joypad / GG handheld buttons.
   Dragon hatches, reaches the star, and gets a new random-like challenge.
*/
#include "SMSlib.h"
#include <stdint.h>
static const unsigned char dragon_tile[32] = {
__DRAGON_TILE__
};
static const unsigned char star_tile[32] = {
__STAR_TILE__
};
static const unsigned char dragon_blink_tile[32] = {
__DRAGON_BLINK_TILE__
};
static unsigned char player_x=20,player_y=58;
static unsigned char star_x=__GOAL_X__,star_y=__GOAL_Y__;
static unsigned char score=0,blink=0,frame=0;

static void draw(void){
    SMS_initSprites();
    SMS_addSprite(player_x,player_y,(blink?3:1));
    SMS_addSprite(star_x,star_y,2);
    SMS_copySpritestoSAT();
}
static void challenge(void){
    score++;
    star_x=(unsigned char)(18u+(score*37u+__SEED_X__)%(__MAX_X__-22u));
    star_y=(unsigned char)(18u+(score*31u+__SEED_Y__)%(__MAX_Y__-22u));
    frame=0;
#ifdef TARGET_GG
    GG_setSpritePaletteColor(2,RGB((score%14u)+1u,13,3));
#else
    SMS_setSpritePaletteColor(2,RGB((score%2u)+2u,3,1));
#endif
}
int main(void){
    unsigned int keys;
    SMS_init();
    SMS_displayOff();
#ifdef TARGET_GG
    GG_setSpritePaletteColor(0,RGB(0,0,0));
    GG_setSpritePaletteColor(1,RGB(15,13,4));
    GG_setSpritePaletteColor(2,RGB(4,14,10));
    GG_setSpritePaletteColor(3,RGB(1,2,4));
#else
    SMS_setSpritePaletteColor(0,RGB(0,0,0));
    SMS_setSpritePaletteColor(1,RGB(3,3,1));
    SMS_setSpritePaletteColor(2,RGB(1,3,2));
    SMS_setSpritePaletteColor(3,RGB(0,0,1));
#endif
    SMS_useFirstHalfTilesforSprites(1);
    SMS_loadTiles(dragon_tile,1,32);
    SMS_loadTiles(star_tile,2,32);
    SMS_loadTiles(dragon_blink_tile,3,32);
    draw();
    SMS_displayOn();
    for(;;){
        SMS_waitForVBlank();
        keys=SMS_getKeysStatus();
        if((keys&PORT_A_KEY_RIGHT)&&player_x<__MAX_X__)player_x++;
        if((keys&PORT_A_KEY_LEFT)&&player_x>4)player_x--;
        if((keys&PORT_A_KEY_UP)&&player_y>4)player_y--;
        if((keys&PORT_A_KEY_DOWN)&&player_y<__MAX_Y__)player_y++;
        if((unsigned char)(player_x-star_x+9u)<18u &&
           (unsigned char)(player_y-star_y+9u)<18u){
            challenge();
        }
        blink=(unsigned char)((frame++&31u)==0u);
        draw();
    }
    return 0;
}
'''
    source=(source.replace("__DRAGON_TILE__",_sms_tile("dragon"))
                  .replace("__STAR_TILE__",_sms_tile("star"))
                  .replace("__DRAGON_BLINK_TILE__",_sms_tile("dragon_blink"))
                  .replace("__GOAL_X__",str(goal_x))
                  .replace("__GOAL_Y__",str(goal_y))
                  .replace("__SEED_X__",str(seed%119))
                  .replace("__SEED_Y__",str((seed//17)%113))
                  .replace("__MAX_X__",str(max_x))
                  .replace("__MAX_Y__",str(max_y)))
    variant="game_gear" if game_gear else "master_system"
    output="gg" if game_gear else "sms"
    define="-DTARGET_GG" if game_gear else ""
    lib="SMSlib_GG.lib" if game_gear else "SMSlib.lib"
    # User-supplied devkitSMS location; excludes all non-free commercial SDKs.
    makefile=("""\
SDCC ?= sdcc
MAKESMS ?= makesms
DEVKITSMS_HOME ?= /opt/devkitSMS
CRT0 ?= $(DEVKITSMS_HOME)/crt0/crt0_sms.rel
SMSLIB ?= $(DEVKITSMS_HOME)/SMSlib/__LIB__
CFLAGS = -mz80 -I$(DEVKITSMS_HOME)/SMSlib/__DEF__
.PHONY: all clean
all: build/dragon.__EXT__
build/dragon.rel: src/main.c
\tmkdir -p build
\t$(SDCC) -c $(CFLAGS) -o $@ $<
build/dragon.ihx: build/dragon.rel
\t$(SDCC) -o $@ -mz80 --no-std-crt0 --data-loc 0xC000 $(CRT0) $< $(SMSLIB)
build/dragon.__EXT__: build/dragon.ihx
\t$(MAKESMS) $< $@
clean:
\trm -rf build
""".replace("__LIB__",lib).replace("__DEF__",define).replace("__EXT__",output))
    return {"src/main.c":source,"Makefile":makefile}
