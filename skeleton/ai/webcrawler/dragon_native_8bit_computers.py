"""Original playable 8-bit homebrew games for five real computer toolchains.

Commodore VIC20, Commodore 128, Atari 400/800 use 6502 cc65 target CRT
and platform-specific video/audio color registers. MSX1 and Amstrad CPC
use z88dk Z80 target conio/keyboard bindings and native display colors.

No commercial ROM/data/title bytes included. This is source-only until
the platform compiler/emulator and actual keyboard/device verify output.
"""
from __future__ import annotations

def _seed(value:int)->int:
    if type(value) is not int or not 0 <= value < 2**32:
        raise ValueError("8-bit machine original game seed must be uint32")
    return value&0xffff or 1

# Minimal memory limits: no dynamic allocation, native conio I/O,
# exact display constraints of each target, bounded chase game state.
SOURCE=r'''/* Original Dragon Legacy Computer game. Native __NAME__ (__CPU__).
   Genuine machine text display + keyboard and memory-mapped color/audio.
   Source uses cc65 or z88dk startup, not SDL/HTML or a PC executable. */
#include <conio.h>
#include <stdint.h>
#include <stdlib.h>
__EXTRA_INCLUDE__
#define FIELD_W __FIELD_W__
#define FIELD_H __FIELD_H__
static unsigned int rng=__SEED__;
static unsigned char hero_x=3,hero_y=5,gem_x=12,gem_y=9;
static unsigned char foe_x=FIELD_W-3,foe_y=FIELD_H-3;
static unsigned char hp=5,level=1,score=0,frame=0,guard=0;
static unsigned int next_rng(void) {
 rng^=rng<<7;rng^=rng>>9;rng^=rng<<8;return rng;
}
static void machine_init(void){
 __MACHINE_INIT__
}
static void machine_pickup(void){
 __MACHINE_PICKUP__
}
static void reset(void) {
 rng=__SEED__;
 hero_x=3;hero_y=5;gem_x=12;gem_y=9;
 foe_x=FIELD_W-3;foe_y=FIELD_H-3;
 hp=5;level=1;score=0;frame=0;guard=0;
 machine_init();
}
static void draw(void){
 unsigned char row,col;
 clrscr();
 gotoxy(0,0);cputs("DRAGON __SHORT_NAME__");
 gotoxy(0,1);cprintf("S:%u L:%u H:%u",score,level,hp);
 for(row=3;row<FIELD_H;row++){
  gotoxy(0,row);
  for(col=0;col<FIELD_W;col++){
   char symbol=' ';
   if(row==3||row==FIELD_H-1||col==0||col==FIELD_W-1)symbol='#';
   else if(col==gem_x&&row==gem_y)symbol='*';
   else if(col==foe_x&&row==foe_y)symbol='X';
   else if(col==hero_x&&row==hero_y)symbol='D';
   cputc(symbol);
  }
 }
 gotoxy(0,FIELD_H);
 cputs("WASD/R/Q");
 if(!hp){gotoxy(2,FIELD_H/2);cputs("DRAGON DOWN - R");}
}
static void advance(char key){
 if(key=='r'||key=='R'){reset();return;}
 if(!hp)return;
 if((key=='a'||key=='A')&&hero_x>1)hero_x--;
 if((key=='d'||key=='D')&&hero_x<FIELD_W-2)hero_x++;
 if((key=='w'||key=='W')&&hero_y>4)hero_y--;
 if((key=='s'||key=='S')&&hero_y<FIELD_H-2)hero_y++;
 if(hero_x==gem_x&&hero_y==gem_y){
  score++;level=1+score/4;
  gem_x=2+(unsigned char)(next_rng()%(FIELD_W-4));
  gem_y=4+(unsigned char)(next_rng()%(FIELD_H-6));
  if(score%5==0&&hp<5)hp++;
  machine_pickup();
 }
 frame++;
 if(guard)guard--;
 if(frame%(11-(level>8?8:level))==0){
  if(foe_x<hero_x)foe_x++;else if(foe_x>hero_x)foe_x--;
  if(foe_y<hero_y)foe_y++;else if(foe_y>hero_y)foe_y--;
 }
 if(hero_x==foe_x&&hero_y==foe_y&&!guard){
  hp--;guard=7;
  foe_x=FIELD_W-3;foe_y=FIELD_H-3;
 }
}
int main(void){
 char key;
 reset();
 for(;;){
  draw();
  key=(char)__READ_KEY__;
  if(key=='q'||key=='Q')break;
  advance(key);
 }
 clrscr();return 0;
}
'''
PLATFORMS={
    "commodore_vic20":{
        "cpu":"MOS 6502","name":"VIC20","short":"VIC20","field_w":"20","field_h":"20",
        "compiler":"cl65","extra":"#include <peekpoke.h>",
        "init":"POKE(0x900F,0x0E); /* VIC-I screen and border colors */",
        "pickup":"POKE(0x900E,0x0F); /* native VIC-I tone/volume register */",
        "read":"cgetc()","target":"vic20","output":"prg","extension":"prg",
    },
    "commodore_128":{
        "cpu":"MOS 8502","name":"Commodore 128","short":"C128","field_w":"39","field_h":"23",
        "compiler":"cl65","extra":"#include <peekpoke.h>",
        "init":"POKE(0xD020,0x06); /* VIC-II border color in 40-col mode */",
        "pickup":"POKE(0xD418,0x0F); /* SID voice volume */",
        "read":"cgetc()","target":"c128","output":"prg","extension":"prg",
    },
    "atari_400_800":{
        "cpu":"MOS 6502","name":"Atari 400/800","short":"ATARI","field_w":"39","field_h":"22",
        "compiler":"cl65","extra":"#include <peekpoke.h>",
        "init":"POKE(0x02C8,0x48); /* ANTIC/GTIA OS shadow color */",
        "pickup":"POKE(0xD201,0xA8); /* POKEY AUDC1 channel timbre */",
        "read":"cgetc()","target":"atari","output":"xex","extension":"xex",
    },
    "msx1":{
        "cpu":"Zilog Z80","name":"MSX1","short":"MSX1","field_w":"31","field_h":"23",
        "compiler":"zcc","extra":"#include <stdio.h>",
        "init":"textcolor(15); /* MSX BIOS-backed conio text foreground */",
        "pickup":"textcolor(10); /* MSX palette feedback for goal */",
        "read":"getch()","target":"msx","output":"bin","extension":"bin",
    },
    "amstrad_cpc":{
        "cpu":"Zilog Z80","name":"Amstrad CPC","short":"CPC","field_w":"31","field_h":"23",
        "compiler":"zcc","extra":"#include <stdio.h>",
        "init":"textcolor(3); /* CPC firmware text palette */",
        "pickup":"textcolor(2); /* CPC collected-crystal ink */",
        "read":"getch()","target":"cpc","output":"bin","extension":"bin",
    },
}
def computer_source(target_id:str,seed:int)->dict[str,str]:
    n=_seed(seed)
    if target_id not in PLATFORMS:
        raise ValueError("unimplemented original 8-bit computer target")
    spec=PLATFORMS[target_id]
    body=SOURCE
    vars={
        "__SEED__":str(n),"__NAME__":spec["name"],"__CPU__":spec["cpu"],
        "__SHORT_NAME__":spec["short"],"__FIELD_W__":spec["field_w"],
        "__FIELD_H__":spec["field_h"],"__EXTRA_INCLUDE__":spec["extra"],
        "__MACHINE_INIT__":spec["init"],"__MACHINE_PICKUP__":spec["pickup"],
        "__READ_KEY__":spec["read"],
    }
    for a,b in vars.items():body=body.replace(a,b)
    if spec["compiler"]=="cl65":
        target=spec["target"]
        make=(
            f"CL65 ?= cl65\nall: build/dragon.{spec['extension']}\n"
            f"build/dragon.{spec['extension']}: src/main.c\n"
            "\t@mkdir -p build\n"
            f"\t$(CL65) -t {target} -O -o $@ $<\n"
            "clean:\n\trm -rf build\n"
        )
    else:
        target=spec["target"]
        make=(
            f"ZCC ?= zcc\nall: build/dragon.{spec['extension']}\n"
            f"build/dragon.{spec['extension']}: src/main.c\n"
            "\t@mkdir -p build\n"
            f"\t$(ZCC) +{target} -clib=ansi -O2 -o $@ $<\n"
            "clean:\n\trm -rf build\n"
        )
    return {
        "src/main.c":body,
        "Makefile":make,
        "README.port.md":(
            f"# Original {spec['name']} Dragon arcade game\n\n"
            f"Native CPU {spec['cpu']}, cross compiler {spec['compiler']}; "
            f"source-level output intent: {spec['extension']}. "
            "The real game uses native conio video/keyboard, platform I/O "
            "and deterministic collectible/pursuer/health mechanics. "
            "Toolchain object format, firmware bootability, screen alignment, "
            "emulator controller inputs and memory consumption still require "
            "independent target checks. Other companies' game content and "
            "proprietary SDKs are not included.\n"
        ),
    }
