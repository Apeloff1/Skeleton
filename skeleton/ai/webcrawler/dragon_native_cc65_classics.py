"""Four additional original 6502 home computer native-game source adapters.

Target-native conio text/keyboard gameplay compiled with documented cc65
toolchains for Commodore PET, Commodore Plus/4, BBC Micro, Oric Atmos.
Native disk/tape wrapping, audio and hardware testing are not claimed.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Classic6502Target:
    id:str
    cc65:str
    name:str
    output:str
    color:bool
    limitation:str

CLASSICS={
 "commodore_pet":Classic6502Target("commodore_pet","pet","COMMODORE PET",
    "prg",False,"PET monochrome VDU, no audio implementation"),
 "commodore_plus4":Classic6502Target("commodore_plus4","plus4","COMMODORE PLUS4",
    "prg",True,"TED color text; no TED audio implementation"),
 "bbc_micro":Classic6502Target("bbc_micro","bbc","BBC MICRO",
    "bin",True,"MOS video text; no SN76489 audio implementation"),
 "oric_atmos":Classic6502Target("oric_atmos","atmos","ORIC ATMOS",
    "bin",True,"Oric video text; no AY audio implementation"),
}

_C=r'''/* Original Dragon 6502 native turn-based maze for the cc65 target.
   Real machine keyboard and text VDU, no WebView, no fake cartridge. */
#include <conio.h>
#include <stdint.h>
#define W 28
#define H 17
#define NAME "__NAME__"
#define SEED __SEED__u
#define COLOUR __COLOR__
static unsigned int rng=SEED;
static unsigned char x,y,starx,stary,foex,foey,gatex,gatey;
static unsigned char hp,score,level,has_key,guard,steps,defeated;
static char level_cells[H][W+1];
static unsigned int random16(void){
 rng^=(unsigned int)(rng<<7);
 rng^=(unsigned int)(rng>>9);
 rng^=(unsigned int)(rng<<8);
 return rng;
}
static void level_start(void){
 unsigned char i,j;
 for(j=0;j<H;j++){
  for(i=0;i<W;i++){
   char c=' ';
   if(i==0||i==W-1||j==0||j==H-1)c='#';
   else if((j==4||j==10)&&i>4&&i<23&&i!=8&&i!=17)c='#';
   else if(i==14&&j>5&&j<15&&j!=8&&j!=12)c='#';
   level_cells[j][i]=c;
  }
  level_cells[j][W]=0;
 }
 x=3;y=2;starx=23;stary=2;foex=24;foey=14;
 gatex=22;gatey=13;has_key=0;guard=0;steps=0;
}
static void reset(void){
 rng=SEED;hp=5;score=0;level=1;defeated=0;
 level_start();
}
static unsigned char passable(unsigned char col,unsigned char row){
 if(col>=W||row>=H)return 0;
 return level_cells[row][col]!='#';
}
static void enemy_turn(void){
 unsigned char nx,ny;
 signed char dx=x>foex?1:x<foex?-1:0;
 signed char dy=y>foey?1:y<foey?-1:0;
 if((steps&1)==0){
  nx=(unsigned char)(foex+dx);
  if(passable(nx,foey))foex=nx;
 }else{
  ny=(unsigned char)(foey+dy);
  if(passable(foex,ny))foey=ny;
 }
 if(foex==x&&foey==y&&!guard){
  if(hp)hp--;
  guard=4;foex=24;foey=14;
  if(!hp)defeated=1;
 }
}
static void keypress(char key){
 unsigned char nx=x,ny=y;
 if(key=='a'||key=='A')nx--;
 else if(key=='d'||key=='D')nx++;
 else if(key=='w'||key=='W')ny--;
 else if(key=='s'||key=='S')ny++;
 else return;
 if(!passable(nx,ny))return;
 x=nx;y=ny;steps++;
 if(guard)guard--;
 if(x==starx&&y==stary&&!has_key){has_key=1;score+=2;}
 if(x==gatex&&y==gatey&&has_key){
  score+=10;level++;
  if(hp<5)hp++;
  level_start();
  foex=(unsigned char)(23-(level%3));
 }
 if(steps%(level>3?1:3)==0)enemy_turn();
}
static void draw(void){
 unsigned char i,j;
 clrscr();
#if COLOUR
 textcolor(7);
#endif
 gotoxy(0,0);cputs(NAME);
 gotoxy(0,1);cprintf("STAGE:%u SCORE:%u HP:%u",level,score,hp);
 for(j=0;j<H;j++){
  gotoxy(0,j+3);
  for(i=0;i<W;i++){
   char c=level_cells[j][i];
   if(i==gatex&&j==gatey)c=has_key?'O':'X';
   if(i==starx&&j==stary&&!has_key)c='*';
   if(i==foex&&j==foey)c='!';
   if(i==x&&j==y)c=guard?'d':'D';
   cputc(c);
  }
 }
 gotoxy(0,21);cputs("WASD MOVE R RESTART Q QUIT");
 gotoxy(0,22);
 if(defeated)cputs("DOWN - PRESS R TO RESTART");
 else if(has_key)cputs("CRYSTAL FOUND: FIND GATE O");
 else cputs("GET THE CRYSTAL * AND GATE X");
}
int main(void){
 char key;
 reset();
 for(;;){
  draw();key=(char)cgetc();
  if(key=='q'||key=='Q')break;
  if(key=='r'||key=='R'){reset();continue;}
  if(!defeated)keypress(key);
 }
 clrscr();return 0;
}
'''

def classic_cc65_source(target_id:str,seed:int)->dict[str,str]:
    if not isinstance(target_id,str) or target_id not in CLASSICS:
        raise ValueError("unknown native 6502 home computer target")
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("6502 source seed must be uint32")
    t=CLASSICS[target_id]
    source=(_C.replace("__NAME__",t.name)
              .replace("__SEED__",str((seed&65535) or 1))
              .replace("__COLOR__","1" if t.color else "0"))
    make=(
      "CL65 ?= cl65\n"
      f"CC65_TARGET := {t.cc65}\n"
      f"OUTPUT := build/dragon.{t.output}\n"
      "all: $(OUTPUT)\n"
      "$(OUTPUT): src/main.c\n"
      "\t@mkdir -p build\n"
      "\t$(CL65) -O -t $(CC65_TARGET) -o $@ $<\n"
      "clean:\n"
      "\trm -rf build\n"
    )
    readme=(
      "# Original native "+t.name+" game\n\n"
      "Actual keyboard-controlled maze, gated crystal, enemy pursuit, "
      "health, restart and chapter progression using target-native cc65 "
      "conio text rendering. Build with the platform-specific target library. "
      "Source-only: compiler, emulator and real-device success not implied. "
      "Hardware-specific limit: "+t.limitation+". "
      "Disk/cassette packaging and audio require further implementation. "
      "No proprietary ROM, BIOS, assets, or SDK keys.\n"
    )
    return {"src/main.c":source,"Makefile":make,"README.port.md":readme}
