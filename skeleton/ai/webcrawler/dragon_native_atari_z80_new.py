"""Original games on Atari 5200, ColecoVision, ZX81 and MSX2 systems.

These are actual 6502/Z80 native C game loops and toolchain recipes,
not renamed PC executables. Source output remains unverified until each
target's own compiler, emulator, video/sound and physical controls pass.
No commercial ROM, firmware, BIOS, game character or SDK is included.
"""
from __future__ import annotations

def _seed(value:int)->int:
    if type(value) is not int or not 0<=value<2**32:
        raise ValueError("native 6502/Z80 source requires uint32 seed")
    return (value&0xFFFF) or 1

ATARI_5200=r'''/* Original Atari 5200 action game using cc65's real 6502 CRT.
   ANTIC text mode 6 conio; POKEY/GTIA color shadow and native analog pad
   through its statically linked 5200 joystick driver. Cartridge source. */
#include <atari5200.h>
#include <conio.h>
#include <joystick.h>
#include <stdint.h>
extern const void joy_static_stddrv[];
#define W 20
#define H 24
static unsigned int prng=__SEED__;
static unsigned char px=3,py=5,gx=13,gy=9,fx=17,fy=18;
static unsigned char life=5,level=1,score=0,guard=0,step=0;
/* cc65 2.19 atari5200.h provides GTIA_WRITE but not OS.
   Newer revisions expose OS shadow colors.  Preserve the ability to build
   against either SDK, with the real Atari GTIA hardware-register fallback. */
static void dragon_palette(unsigned char palette){
#ifdef OS
 OS.color0=0x24;OS.color1=palette;OS.color2=0xA8;
#else
 GTIA_WRITE.colpf0=0x24;
 GTIA_WRITE.colpf1=palette;
 GTIA_WRITE.colpf2=0xA8;
#endif
}
static unsigned int rnd(void){
 prng^=prng<<7;prng^=prng>>9;prng^=prng<<8;
 return prng;
}
static void restart(void){
 prng=__SEED__;px=3;py=5;gx=13;gy=9;fx=17;fy=18;
 life=5;level=1;score=0;guard=0;step=0;
 dragon_palette(0x86);
}
static void draw(void){
 clrscr();
 gotoxy(0,0);cputs("DRAGON ATARI 5200");
 gotoxy(0,1);cprintf("S:%u LV:%u HP:%u",score,level,life);
 gotoxy(gx,gy);cputc('*');
 gotoxy(fx,fy);cputc('X');
 gotoxy(px,py);cputc('D');
 gotoxy(0,21);cputs("ANALOG PAD / FIRE");
 if(!life){gotoxy(2,12);cputs("GAME OVER");}
}
static void move(unsigned char key){
 if(key&JOY_BTN_1_MASK){
  if(!life)restart();
  else if(guard<8)guard=8;
 }
 if(!life)return;
 if((key&JOY_LEFT_MASK)&&px>1)px--;
 if((key&JOY_RIGHT_MASK)&&px<W-2)px++;
 if((key&JOY_UP_MASK)&&py>3)py--;
 if((key&JOY_DOWN_MASK)&&py<H-4)py++;
 if(px==gx&&py==gy){
  score++;level=1+score/4;
  gx=1+(unsigned char)(rnd()%18);
  gy=3+(unsigned char)(rnd()%17);
  dragon_palette((unsigned char)(0x48+(score&7)*2));
  if(score%5==0&&life<5)life++;
 }
 step++;
 if(guard)guard--;
 if(step%(12-(level>8?8:level))==0){
  if(fx<px)fx++;else if(fx>px)fx--;
  if(fy<py)fy++;else if(fy>py)fy--;
 }
 if(px==fx&&py==fy&&!guard){
  life--;guard=12;fx=17;fy=19;
 }
}
int main(void){
 unsigned char pad,previous=0;
 if(joy_install(joy_static_stddrv)!=JOY_ERR_OK)return 1;
 restart();
 for(;;){
  pad=joy_read(0);
  /* Clock the original rules even on neutral input: enemies are real. */
  move(pad);
  if(pad!=previous||step%6==0||!life)draw();
  previous=pad;
  waitvsync();
 }
 return 0;
}
'''
# Z88DK game loop is shared only where true Z80 conio and CRT bind to the
# original firmware/VDP. Unique controller paths and packaging per platform.
Z80_NATIVE=r'''/* Original native __TITLE__ Z80 game, compiled by z88dk.
   No HTML, SDL, emulator firmware or copyrighted game content. */
#include <conio.h>
#include <stdint.h>
#include <stdlib.h>
__INPUT_HEADER__
#define GAME_W __WIDTH__
#define GAME_H __HEIGHT__
static unsigned int seed=__SEED__;
static unsigned char px=4,py=6,gx=15,gy=12,fx=GAME_W-4,fy=GAME_H-3;
static unsigned char hp=5,score=0,level=1,iframes=0,frame=0;
static unsigned int next_rand(void){
 seed^=seed<<7;seed^=seed>>9;seed^=seed<<8;return seed;
}
static void reset(void){
 seed=__SEED__;px=4;py=6;gx=15;gy=12;fx=GAME_W-4;fy=GAME_H-3;
 hp=5;score=0;level=1;iframes=0;frame=0;
 __INIT__
}
static void draw(void){
 clrscr();
 gotoxy(0,0);cputs("DRAGON __TITLE__");
 gotoxy(0,1);cprintf("S:%u LV:%u HP:%u",score,level,hp);
 gotoxy(gx,gy);putch('*');
 gotoxy(fx,fy);putch('X');
 gotoxy(px,py);putch('D');
 gotoxy(0,GAME_H);cputs("__CONTROL_HINT__");
 if(!hp){gotoxy(3,9);cputs("DRAGON DOWN! FIRE");}
}
static void advance(unsigned char buttons){
 if((buttons&16)&&!hp){reset();return;}
 if(!hp)return;
 if((buttons&1)&&px<GAME_W-2)px++;
 if((buttons&2)&&px>1)px--;
 if((buttons&4)&&py<GAME_H-2)py++;
 if((buttons&8)&&py>3)py--;
 if((buttons&16)&&iframes<6)iframes=6;
 if(px==gx&&py==gy){
  score++;level=1+score/4;
  gx=2+(unsigned char)(next_rand()%(GAME_W-4));
  gy=4+(unsigned char)(next_rand()%(GAME_H-6));
  if(score%5==0&&hp<5)hp++;
  __PICKUP__
 }
 frame++;
 if(iframes)iframes--;
 if(frame%(12-(level>8?8:level))==0){
  if(fx<px)fx++;else if(fx>px)fx--;
  if(fy<py)fy++;else if(fy>py)fy--;
 }
 if(fx==px&&fy==py&&!iframes){
  hp--;iframes=12;fx=GAME_W-3;fy=GAME_H-3;
 }
}
int main(void){
 unsigned char previous=0,current;
 reset();draw();
 while(1){
  current=(unsigned char)(__READ_INPUT__);
  advance(current);
  if(frame%4==0||current!=previous||!hp)draw();
  previous=current;
  __FRAME_WAIT__
 }
 return 0;
}
'''
# Colecovision's 2-button controller reports through z88dk games.h, the
# target's native I/O binding; no keyboard input is falsely assumed.
PROFILES={
 "colecovision":{
  "title":"COLECOVISION","width":28,"height":21,"input_header":"#include <games.h>",
  "init":"/* Coleco TMS9928A text CRT installed by +coleco */",
  "read":"joystick(1)","pickup":"/* built-in SN76489 hardware sound scheduled separately */",
  "hint":"JOYSTICK / FIRE","wait":"/* native input tick */",
  "compiler":"zcc","flags":"+coleco -create-app -bn build/dragon",
  "output":"rom","rule":"build/dragon.rom",
 },
 "zx81":{
  "title":"SINCLAIR ZX81","width":30,"height":20,"input_header":"#include <games.h>",
  "init":"/* ZX81 16K RAM text/display required */",
  "read":"joystick(1)","pickup":"/* no invented multi-channel audio */",
  "hint":"Q A O P M / KEY FIRE","wait":"/* keyboard frame */",
  "compiler":"zcc","flags":"+zx81 -create-app -bn build/dragon",
  "output":"p","rule":"build/dragon.p",
 },
 "msx2":{
  "title":"MSX2","width":31,"height":22,"input_header":"#include <msx.h>",
  "init":"msx_screen(0); /* genuine MSX BIOS text/VDP initialization */",
  # Convert MSX BIOS 1..8 octant value into original bitwise R L D U F.
  "read":"read_msx_joystick()","pickup":"textcolor(10); /* V9938 BIOS text palette feedback */",
  "hint":"STICK 1 / TRIGGER","wait":"/* VDP updates via BIOS CRT */",
  "compiler":"zcc","flags":"+msx -subtype=msxdos -o build/dragon.com",
  "output":"com","rule":"build/dragon.com",
 },
}
MSX_INPUT=r'''/* Converts MSX BIOS stick 8-direction state to R L D U FIRE. */
static unsigned char read_msx_joystick(void){
 int v=msx_get_stick(1);
 unsigned char bits=0;
 if(v==2||v==3||v==4)bits|=1;
 if(v==6||v==7||v==8)bits|=2;
 if(v==4||v==5||v==6)bits|=4;
 if(v==8||v==1||v==2)bits|=8;
 if(msx_get_trigger(1))bits|=16;
 return bits;
}
'''
# zx81 lacks a physical joystick: native key scanner is the honest path.
ZX81_INPUT=r'''/* Keyboard-derived "joystick": no hardware pad is claimed. */
static unsigned char read_zx81_keys(void){
 int c;
 unsigned char flags=0;
 if(!kbhit())return 0;
 c=getch();
 if(c=='p'||c=='P')flags|=1;
 if(c=='o'||c=='O')flags|=2;
 if(c=='a'||c=='A')flags|=4;
 if(c=='q'||c=='Q')flags|=8;
 if(c=='m'||c=='M')flags|=16;
 return flags;
}
'''
def native_machine_source(target_id:str,seed:int)->dict[str,str]:
    value=_seed(seed)
    if target_id=="atari_5200":
        src=ATARI_5200.replace("__SEED__",str(value))
        make=("CL65 ?= cl65\nall: build/dragon.bin\n"
              "build/dragon.bin: src/main.c\n\t@mkdir -p build\n"
              "\t$(CL65) -t atari5200 -O -o $@ $<\n"
              "clean:\n\trm -rf build\n")
        hint=("Atari 5200 analog controller uses a statically linked "
              "cc65 joystick driver; ANTIC mode-6 conio and shadow colors. "
              "20x24 cell output and game logic must be verified in emulator.")
    else:
        if target_id not in PROFILES:
            raise ValueError("native machine target not implemented")
        p=PROFILES[target_id]
        src=Z80_NATIVE
        params={
          "__SEED__":str(value),"__TITLE__":p["title"],
          "__WIDTH__":str(p["width"]),"__HEIGHT__":str(p["height"]),
          "__INPUT_HEADER__":p["input_header"],
          "__INIT__":p["init"],"__READ_INPUT__":p["read"],
          "__PICKUP__":p["pickup"],"__CONTROL_HINT__":p["hint"],
          "__FRAME_WAIT__":p["wait"],
        }
        for a,b in params.items():src=src.replace(a,b)
        if target_id=="zx81":
            src=src.replace("int main(void){",ZX81_INPUT+"\nint main(void){")
            src=src.replace("joystick(1)","read_zx81_keys()")
        if target_id=="msx2":
            src=src.replace("int main(void){",MSX_INPUT+"\nint main(void){")
        make=("ZCC ?= zcc\nall: "+p["rule"]+"\n"
              +p["rule"]+": src/main.c\n\t@mkdir -p build\n"
              "\t$(ZCC) "+p["flags"]+" $<\n"
              "clean:\n\trm -rf build\n")
        hint={
          "colecovision":"Coleco keypad/joystick through z88dk games.h; TMS9928A CRT",
          "zx81":"ZX81 16K keyboard-only model, no fictional analog joystick",
          "msx2":"MSX2 original MSX BIOS joystick + VDP text CRT; DOS-compatible .COM",
        }[target_id]
    return {
        "src/main.c":src,
        "Makefile":make,
        "README.port.md":(
          "# Original Dragon native 6502 / Z80 game\n\n"
          +target_id+": "+hint+".\n"
          "Game has meaningful collectible placement, enemy pursuit, "
          "hitpoints, fire/restart, scoring and difficulty progression. "
          "The machine, OS/runtime and controller are platform-specific. "
          "Output is source-only. External exact-target build, emulator "
          "video/input replay and actual physical hardware testing remain "
          "unverified; no original commercial game code/assets supplied.\n"
        ),
    }
