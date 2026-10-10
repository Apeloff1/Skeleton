"""Original native Motorola 68000 game sources for three incompatible OS ABIs.

TOS/GEMDOS on Atari ST, Kickstart 1.3 Intuition/graphics libraries on
Amiga 500, and Human68k DOS/IOCS on Sharp X68000 all have distinct
source, build commands, input APIs and output formats. Never emit binary
artifacts, firmware, OS ROM images, licensed sprites or cloned games.

Compiler and real-hardware claims require separate receipts.
"""
from __future__ import annotations

def _seed(seed:int)->int:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Dragon M68K seed must be unsigned 32-bit integer")
    return seed or 1

ATARI_ST=r'''/* ORIGINAL DRAGON ST / Atari ST TOS, 68000.
   Real GEMDOS/BIOS text and input from osbind.h; NO Linux SDL.
   A deterministic turn-stepped crystal collector with a moving predator,
   damage, invulnerability, levels, progression and reset. */
#include <osbind.h>
#include <stdio.h>
#include <stdint.h>
#define W 36
#define H 18
static unsigned long rng=__SEED__UL;
static int hx,hy,gx,gy,fx,fy,health,score,level,frames,shield;
static unsigned long rnd(void) {
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void) {
 rng=__SEED__UL;hx=4;hy=6;gx=19;gy=11;fx=30;fy=15;
 health=5;score=0;level=1;frames=0;shield=0;
}
static void draw(void) {
 int x,y;
 char hud[80];
 Cconws("\033EORIGINAL DRAGON ATARI ST - TOS / GEMDOS\r\n");
 sprintf(hud,"Crystals: %d  Stage: %d  Lives: %d\r\n",score,level,health);
 Cconws(hud);
 Cconws("W/A/S/D move, R restart, Q quit\r\n");
 for(y=0;y<H;y++){
  for(x=0;x<W;x++){
   int c=' ';
   if(x==0||y==0||x==W-1||y==H-1)c='#';
   else if(x==gx&&y==gy)c='*';
   else if(x==fx&&y==fy)c='X';
   else if(x==hx&&y==hy)c=shield?'@':'D';
   Bconout(2,c);
  }
  Cconws("\r\n");
 }
 if(!health)Cconws("HATCHLING DOWN. Press R to restart.\r\n");
}
static void move(int dx,int dy){
 hx+=dx;hy+=dy;
 if(hx<1)hx=1;if(hx>W-2)hx=W-2;
 if(hy<1)hy=1;if(hy>H-2)hy=H-2;
}
static void step(void){
 frames++;
 if(shield)shield--;
 if(hx==gx&&hy==gy){
  score++;level=1+score/4;
  gx=2+(int)(rnd()%(W-4));gy=2+(int)(rnd()%(H-4));
  if(score%5==0&&health<5)health++;
 }
 if(frames%(7-(level>5?5:level))==0){
  if(hx>fx)fx++;else if(hx<fx)fx--;
  if(hy>fy)fy++;else if(hy<fy)fy--;
 }
 if(hx==fx&&hy==fy&&!shield){
  health--;shield=4;fx=W-3;fy=H-3;
 }
}
int main(void){
 reset();
 for(;;){
  int c; draw();
  c=(int)Crawcin(); c&=255;
  if(c=='q'||c=='Q')break;
  if(c=='r'||c=='R'){reset();continue;}
  if(!health)continue;
  if(c=='a'||c=='A')move(-1,0);
  if(c=='d'||c=='D')move(1,0);
  if(c=='w'||c=='W')move(0,-1);
  if(c=='s'||c=='S')move(0,1);
  step();
 }
 Cconws("\033E");return 0;
}
'''

AMIGA=r'''/* ORIGINAL DRAGON AMIGA 500 / Kickstart 1.3 native libraries.
   Intuition window IDCMP_VANILLAKEY and genuine graphics.library
   RastPort rectangles. No SDL, browser, image assets, or Workbench game.
   Native graphics and keyboard do not imply physical 50Hz verification. */
#include <exec/types.h>
#include <exec/libraries.h>
#include <proto/exec.h>
#include <proto/intuition.h>
#include <proto/graphics.h>
#include <intuition/intuition.h>
#include <intuition/intuitionbase.h>
#include <graphics/rastport.h>
#include <graphics/gfxbase.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
struct IntuitionBase *IntuitionBase;
struct GfxBase *GfxBase;
static uint32_t rng=__SEED__UL;
static int x,y,crystal_x,crystal_y,hp,score,stage,pred_x,pred_y,ticks,shield;
static struct NewWindow window_spec={
 20,14,320,208,0,1,IDCMP_VANILLAKEY|IDCMP_CLOSEWINDOW,
 WFLG_CLOSEGADGET|WFLG_DRAGBAR|WFLG_DEPTHGADGET|
 WFLG_ACTIVATE|WFLG_SMART_REFRESH,
 NULL,NULL,(UBYTE*)"Dragon: original Amiga adventure",
 NULL,NULL,0,0,0,0,WBENCHSCREEN
};
static uint32_t next_rng(void){
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void){
 rng=__SEED__UL;x=24;y=45;crystal_x=172;crystal_y=100;
 hp=5;score=0;stage=1;pred_x=274;pred_y=151;ticks=0;shield=0;
}
static void paint(struct Window *win) {
 struct RastPort *rp=win->RPort;
 char label[96];
 SetAPen(rp,0);RectFill(rp,1,10,310,198);
 SetAPen(rp,1);
 sprintf(label,"CRYSTALS:%d STAGE:%d HP:%d",score,stage,hp);
 Move(rp,10,24);Text(rp,label,(LONG)strlen(label));
 Move(rp,10,191);Text(rp,"WASD move  R reset  Q quit",25);
 SetAPen(rp,2);RectFill(rp,crystal_x,crystal_y,crystal_x+10,crystal_y+10);
 SetAPen(rp,3);RectFill(rp,pred_x,pred_y,pred_x+11,pred_y+11);
 if(!shield || ticks%2==0){
  SetAPen(rp,1);RectFill(rp,x,y,x+11,y+11);
 }
 if(!hp){
  SetAPen(rp,3);RectFill(rp,55,84,260,119);
  SetAPen(rp,1);Move(rp,69,103);Text(rp,"DRAGON DOWN - R RESET",21);
 }
}
static void update(int dx,int dy){
 if(!hp)return;
 x+=dx*7;y+=dy*7;
 if(x<8)x=8;if(x>290)x=290;
 if(y<33)y=33;if(y>166)y=166;
 ticks++;if(shield)shield--;
 if(x<crystal_x+11 && x+11>crystal_x &&
    y<crystal_y+11 && y+11>crystal_y) {
  score++;stage=1+score/4;
  crystal_x=10+(int)(next_rng()%280);
  crystal_y=38+(int)(next_rng()%124);
  if(score%5==0&&hp<5)hp++;
 }
 if(ticks%(8-(stage>6?6:stage))==0) {
  pred_x+=(x>pred_x?5:-5);pred_y+=(y>pred_y?5:-5);
 }
 if(x<pred_x+12&&x+12>pred_x&&y<pred_y+12&&y+12>pred_y&&!shield){
  hp--;shield=4;pred_x=272;pred_y=154;
 }
}
int main(void){
 struct Window *win;
 int running=1;
 IntuitionBase=(struct IntuitionBase*)OpenLibrary("intuition.library",0);
 GfxBase=(struct GfxBase*)OpenLibrary("graphics.library",0);
 if(!IntuitionBase||!GfxBase){
  if(GfxBase)CloseLibrary((struct Library*)GfxBase);
  if(IntuitionBase)CloseLibrary((struct Library*)IntuitionBase);
  return 1;
 }
 win=OpenWindow(&window_spec);
 if(!win){CloseLibrary((struct Library*)GfxBase);CloseLibrary((struct Library*)IntuitionBase);return 2;}
 reset();paint(win);
 while(running){
  struct IntuiMessage *m;
  WaitPort(win->UserPort);
  while((m=(struct IntuiMessage*)GetMsg(win->UserPort))!=NULL){
   ULONG kind=m->Class;
   UWORD key=m->Code;
   ReplyMsg((struct Message*)m);
   if(kind==IDCMP_CLOSEWINDOW){running=0;break;}
   if(kind!=IDCMP_VANILLAKEY)continue;
   if(key=='q'||key=='Q'){running=0;break;}
   if(key=='r'||key=='R'){reset();paint(win);continue;}
   if(key=='a'||key=='A')update(-1,0);
   if(key=='d'||key=='D')update(1,0);
   if(key=='w'||key=='W')update(0,-1);
   if(key=='s'||key=='S')update(0,1);
   paint(win);
  }
 }
 CloseWindow(win);
 CloseLibrary((struct Library*)GfxBase);
 CloseLibrary((struct Library*)IntuitionBase);
 return 0;
}
'''

X68000=r'''/* Original Sharp X68000 Human68k / Motorola 68000.
   Uses native Human68k DOS console traps, not an Amiga/ST binary.
   Project links as m68k Human68k ELF, then elf2x68k relocatable X-file.
   Original 2D maze hunt: gather stars, evade hunter, progress and retry. */
#include <sys/dos.h>
#include <stdint.h>
#include <stdio.h>
#define W 42
#define H 19
static uint32_t rng=__SEED__UL;
static int px,py,starx,stary,foex,foey,score,level,hp,turn,shield;
static uint32_t next_rng(void){
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void){
 rng=__SEED__UL;px=5;py=5;starx=26;stary=12;
 foex=36;foey=16;score=0;level=1;hp=5;turn=0;shield=0;
}
static void put(int ch){_dos_putchar(ch);}
static void label(const char *str){while(*str)put((unsigned char)*str++);}
static void frame(void){
 int x,y;char hud[100];
 label("\033[2J\033[H");
 label("ORIGINAL DRAGON SHARP X68000 / HUMAN68K\r\n");
 sprintf(hud,"CRYSTALS:%d  LEVEL:%d  LIVES:%d\r\n",score,level,hp);
 label(hud);label("WASD move; R retry; Q quit\r\n");
 for(y=0;y<H;y++){
  for(x=0;x<W;x++){
   int ch=' ';
   if(x==0||y==0||x==W-1||y==H-1)ch='#';
   else if(x==starx&&y==stary)ch='*';
   else if(x==foex&&y==foey)ch='X';
   else if(x==px&&y==py)ch=shield?'@':'D';
   put(ch);
  }
  label("\r\n");
 }
 if(!hp)label("HATCHLING DOWN. Press R to restart.\r\n");
}
static void move(int dx,int dy){
 if(!hp)return;
 px+=dx;py+=dy;
 if(px<1)px=1;if(px>W-2)px=W-2;
 if(py<1)py=1;if(py>H-2)py=H-2;
 turn++;if(shield)shield--;
 if(px==starx&&py==stary){
  score++;level=1+score/4;
  starx=2+(int)(next_rng()%(W-4));stary=2+(int)(next_rng()%(H-4));
  if(score%5==0&&hp<5)hp++;
 }
 if(turn%(7-(level>5?5:level))==0){
  foex+=(px>foex?1:-1);foey+=(py>foey?1:-1);
 }
 if(px==foex&&py==foey&&!shield){
  hp--;shield=4;foex=W-4;foey=H-4;
 }
}
int main(void){
 int key;reset();
 for(;;){
  frame();key=_dos_getchar()&255;
  if(key=='q'||key=='Q')break;
  if(key=='r'||key=='R'){reset();continue;}
  if(key=='a'||key=='A')move(-1,0);
  if(key=='d'||key=='D')move(1,0);
  if(key=='w'||key=='W')move(0,-1);
  if(key=='s'||key=='S')move(0,1);
 }
 label("\033[2J\033[H");return 0;
}
'''

def motorola_native_source(target:str,seed:int)->dict[str,str]:
    n=_seed(seed)
    if target=="atari_st":
        files={
          "src/main.c":ATARI_ST.replace("__SEED__",str(n)),
          "Makefile":(
            "CC = m68k-atari-mint-gcc\n"
            "all: build/dragon.tos\n"
            "build/dragon.tos: src/main.c\n"
            "\t@mkdir -p build\n"
            "\t$(CC) -m68000 -O2 -Wall -o $@ $<\n"
            "clean:\n\trm -rf build\n"),
        }
        tool="m68k-atari-mint-gcc / TOS GEMDOS"
        output="tos"
    elif target=="amiga_500":
        files={
          "src/main.c":AMIGA.replace("__SEED__",str(n)),
          "Makefile":(
            "VBCC ?= vc\n"
            "all: build/dragon\n"
            "build/dragon: src/main.c\n"
            "\t@mkdir -p build\n"
            "\t$(VBCC) +kick13 -O2 -o $@ $<\n"
            "clean:\n\trm -rf build\n"),
        }
        tool="vbcc +kick13 / Kickstart Intuition graphics"
        output="amiga_hunk"
    elif target=="sharp_x68000":
        files={
          "src/main.c":X68000.replace("__SEED__",str(n)),
          "Makefile":(
            "CC = m68k-human68k-gcc\n"
            "ELF2X ?= elf2x68k\n"
            "all: build/dragon.x\n"
            "build/dragon.elf: src/main.c\n"
            "\t@mkdir -p build\n"
            "\t$(CC) -m68000 -O2 -Wall -o $@ $< -ldos\n"
            "build/dragon.x: build/dragon.elf\n"
            "\t$(ELF2X) $< $@\n"
            "clean:\n\trm -rf build\n"),
        }
        tool="human68k-gcc/newlib + elf2x68k converter"
        output="x"
    else:
        raise ValueError("unknown native Motorola 68000 source target")
    files["dragon-m68k-contract.json"]=(
        '{"schema":"skeleton.ai.dragon.m68k_native.v1","target":"'+target+
        '","compiler_status":"source_generated","emulator_status":"unverified",'
        '"real_device_status":"unverified","output":"'+output+'"}\n'
    )
    files["README.port.md"]=(
        "# Original Dragon "+target+" 68000 homebrew\n\n"
        "Architecture: Motorola 68000, genuine distinct host OS API. "
        "Toolchain: "+tool+". Original game has keyboard input, pickups, "
        "progressive difficulty, collision/lives and reset. Source only: "
        "requires real installed cross compiler, matching system libraries, "
        "native binary format verification, emulator controller/video replay "
        "and physical hardware testing. No commercial images or firmware.\n"
    )
    return files
