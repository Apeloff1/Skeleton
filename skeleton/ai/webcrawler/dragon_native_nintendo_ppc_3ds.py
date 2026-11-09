"""Three genuinely native open-toolchain Nintendo homebrew game backends.

Nintendo GameCube (libogc PAD/XFB), Wii (libogc WPAD/XFB), and Nintendo
3DS (libctru/citro2d stereoscopic console). Source generation does NOT imply
successful devkitPro compilation, emulator behavior, licensed release or
physical-console testing.
"""
from __future__ import annotations

def _seed(seed:int)->int:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("native console game seed must be uint32")
    return seed or 1

OGC_GAME=r'''/* Original Dragon Quest: libogc GameCube/Wii native gameplay.
   Hardware video XFB and native controllers, not an SDL/WebView wrapper. */
#include <gccore.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#ifdef DRAGON_WII
#include <wiiuse/wpad.h>
#endif
#define GRID_W 34
#define GRID_H 18
#define ENEMY_COUNT 3
typedef struct {int x,y;}Pos;
static Pos hero,star,enemies[ENEMY_COUNT];
static int lives=5,score=0,level=1,guard=0,frame=0;
static uint32_t rng=__SEED__u;
static uint32_t random_next(void) {
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
}
static void reset(void) {
 rng=__SEED__u;hero.x=4;hero.y=6;
 star.x=22;star.y=12;level=1;score=0;lives=5;guard=0;frame=0;
 for(int i=0;i<ENEMY_COUNT;i++){
  enemies[i].x=29-i*7;enemies[i].y=3+i*4;
 }
}
static void update(int dx,int dy,int action) {
 if(action)reset();
 if(!lives)return;
 if(dx<-1)dx=-1;if(dx>1)dx=1;
 if(dy<-1)dy=-1;if(dy>1)dy=1;
 hero.x+=dx;hero.y+=dy;
 if(hero.x<1)hero.x=1;if(hero.x>GRID_W-2)hero.x=GRID_W-2;
 if(hero.y<1)hero.y=1;if(hero.y>GRID_H-2)hero.y=GRID_H-2;
 if(hero.x==star.x&&hero.y==star.y){
  score++;level=1+score/4;star.x=2+(int)(random_next()%30);
  star.y=2+(int)(random_next()%14);
  if(score%5==0&&lives<5)lives++;
 }
 if(guard)guard--;
 frame++;
 for(int i=0;i<ENEMY_COUNT;i++) {
  if(frame%(22-i*3-(level>7?7:level))==0) {
   if(hero.x>enemies[i].x)enemies[i].x++;
   else if(hero.x<enemies[i].x)enemies[i].x--;
   if(hero.y>enemies[i].y)enemies[i].y++;
   else if(hero.y<enemies[i].y)enemies[i].y--;
  }
  if(hero.x==enemies[i].x&&hero.y==enemies[i].y&&!guard){
   lives--;guard=45;
   enemies[i].x=GRID_W-3-i*4;enemies[i].y=GRID_H-3;
  }
 }
}
static void draw(void) {
 printf("\x1b[H\x1b[2J");
 printf("ORIGINAL DRAGON - __PLATFORM__\n");
 printf("Crystals: %d | Level: %d | HP: %d\n",score,level,lives);
 printf("D-PAD to move | A to reset | HOME/START exit\n");
 for(int y=0;y<GRID_H;y++){
  for(int x=0;x<GRID_W;x++){
   char tile=' ';
   if(x==0||y==0||x==GRID_W-1||y==GRID_H-1)tile='#';
   else if(x==star.x&&y==star.y)tile='*';
   else if(x==hero.x&&y==hero.y)tile=guard?'@':'D';
   else {
    for(int i=0;i<ENEMY_COUNT;i++)
     if(x==enemies[i].x&&y==enemies[i].y)tile='X';
   }
   putchar(tile);
  }
  putchar('\n');
 }
 if(!lives)printf("HATCHLING DOWN! A to restart.\n");
}
int main(int argc,char**argv) {
 (void)argc;(void)argv;
 VIDEO_Init();
 PAD_Init();
#ifdef DRAGON_WII
 WPAD_Init();
#endif
 GXRModeObj*mode=VIDEO_GetPreferredMode(NULL);
 VIDEO_Configure(mode);
 void*framebuffer=MEM_K0_TO_K1(SYS_AllocateFramebuffer(mode));
 console_init(framebuffer,20,30,mode->fbWidth,mode->xfbHeight,
              mode->fbWidth*VI_DISPLAY_PIX_SZ);
 VIDEO_SetNextFramebuffer(framebuffer);
 VIDEO_SetBlack(FALSE);
 VIDEO_Flush();
 VIDEO_WaitVSync();
 reset();
 for(;;){
  PAD_ScanPads();
  u16 held=PAD_ButtonsHeld(0),pressed=PAD_ButtonsDown(0);
  int dx=(!!(held&PAD_BUTTON_RIGHT))-(!!(held&PAD_BUTTON_LEFT));
  int dy=(!!(held&PAD_BUTTON_DOWN))-(!!(held&PAD_BUTTON_UP));
  if(pressed&PAD_BUTTON_START)break;
  int restart=!!(pressed&PAD_BUTTON_A);
#ifdef DRAGON_WII
  WPAD_ScanPads();
  u32 wii=WPAD_ButtonsHeld(0),newpress=WPAD_ButtonsDown(0);
  if(newpress&WPAD_BUTTON_HOME)break;
  dx+=(!!(wii&WPAD_BUTTON_RIGHT))-(!!(wii&WPAD_BUTTON_LEFT));
  dy+=(!!(wii&WPAD_BUTTON_DOWN))-(!!(wii&WPAD_BUTTON_UP));
  restart|=!!(newpress&WPAD_BUTTON_A);
#endif
  update(dx,dy,restart);
  if(frame%2==0||!lives)draw();
  VIDEO_WaitVSync();
 }
#ifdef DRAGON_WII
 WPAD_Shutdown();
#endif
 return 0;
}
'''
OGC_MAKE=r'''# Original native libogc Nintendo __PLATFORM__ homebrew.
# DEVKITPRO=/opt/devkitpro DEVKITPPC=$DEVKITPRO/devkitPPC
ifeq ($(strip $(DEVKITPRO)),)
$(error DEVKITPRO SDK must be installed)
endif
ifeq ($(strip $(DEVKITPPC)),)
$(error DEVKITPPC SDK must be installed)
endif
include $(DEVKITPPC)/__RULES__
TARGET := dragon
OFILES := build/main.o
ARCH := -mogc -mcpu=750 -meabi -mhard-float
CFLAGS := $(ARCH) -O2 -Wall -Wextra -I$(LIBOGC_INC) __FLAGS__
LDFLAGS := $(ARCH)
LIBS := __LIBS__ -lm
LIBPATHS := -L$(LIBOGC_LIB)
all: build/dragon.dol
build/main.o: src/main.c
	@mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@
build/dragon.elf: build/main.o
	$(CC) $(LDFLAGS) -o $@ $< $(LIBPATHS) $(LIBS)
build/dragon.dol: build/dragon.elf
	elf2dol $< $@
clean:
	rm -rf build
'''
def gamecube_source(seed:int)->dict[str,str]:
    n=_seed(seed)
    src=OGC_GAME.replace("__SEED__",str(n)).replace("__PLATFORM__","GAMECUBE")
    make=(OGC_MAKE.replace("__PLATFORM__","GameCube")
          .replace("__RULES__","gamecube_rules")
          .replace("__FLAGS__","")
          .replace("__LIBS__","-logc"))
    return {"src/main.c":src,"Makefile":make,
        "README.port.md":"# Original GameCube libogc game\n"
          "PAD controller, 640-class XFB text console, deterministic enemy "
          "chase, score/health, D-pad movement, GameCube DOL target. "
          "SDK build, controller video replay and hardware run unverified.\n"}

def wii_source(seed:int)->dict[str,str]:
    n=_seed(seed)
    src=OGC_GAME.replace("__SEED__",str(n)).replace("__PLATFORM__","WII")
    make=(OGC_MAKE.replace("__PLATFORM__","Wii")
          .replace("__RULES__","wii_rules")
          .replace("__FLAGS__","-DDRAGON_WII=1")
          .replace("__LIBS__","-lwiiuse -lbte -logc"))
    return {"src/main.c":src,"Makefile":make,
        "README.port.md":"# Original Wii libogc homebrew\n"
          "Real Wii Remote WPAD/Home and GameCube PAD inputs, XFB output, "
          "native PPC game state, increasing pursuer AI and scoring. "
          "devkitPPC/libogc/wiiuse, emulator run and physical controls unverified.\n"}

THREEDS=r'''/* Original Nintendo 3DS game: real citro2d graphics and libctru input.
   Top game framebuffer and bottom touchscreen/console have distinct roles. */
#include <3ds.h>
#include <citro2d.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define WIDTH 400
#define HEIGHT 240
#define FOES 4
static int x=45,y=72,starx=260,stary=115,hp=5,score=0,level=1,tick=0,iframes=0;
static int ex[FOES]={320,330,315,345},ey[FOES]={80,120,170,200};
static uint32_t rng=__SEED__u;
static uint32_t next_rng(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void reset(void){
 x=45;y=72;starx=260;stary=115;hp=5;score=0;level=1;tick=0;iframes=0;
 rng=__SEED__u;
 for(int i=0;i<FOES;i++){ex[i]=320+i*6;ey[i]=60+i*39;}
}
static void move(int dx,int dy){
 if(!hp)return;
 x+=dx;y+=dy;
 if(x<8)x=8;if(x>WIDTH-28)x=WIDTH-28;
 if(y<8)y=8;if(y>HEIGHT-28)y=HEIGHT-28;
}
static void update(void){
 tick++;
 if(iframes)iframes--;
 if(!hp)return;
 if(abs(x-starx)<17&&abs(y-stary)<17){
  score++;level=1+score/4;
  starx=20+(int)(next_rng()%360);
  stary=18+(int)(next_rng()%200);
  if(score%5==0&&hp<5)hp++;
 }
 for(int i=0;i<FOES;i++){
  if(tick%(12+i*3-(level>7?7:level))==0){
   if(x>ex[i])ex[i]++;else if(x<ex[i])ex[i]--;
   if(y>ey[i])ey[i]++;else if(y<ey[i])ey[i]--;
  }
  if(abs(x-ex[i])<15&&abs(y-ey[i])<15&&!iframes){
   hp--;iframes=50;
   ex[i]=310+i*5;ey[i]=25+i*45;
  }
 }
}
static void render(C3D_RenderTarget*top){
 C3D_FrameBegin(C3D_FRAME_SYNCDRAW);
 C2D_TargetClear(top,C2D_Color32(12,24,48,255));
 C2D_SceneBegin(top);
 for(int i=0;i<10;i++)
  C2D_DrawRectSolid(0,i*24,0,400,1,C2D_Color32(42,61,79,255));
 for(int i=0;i<hp;i++)
  C2D_DrawRectSolid(10+i*22,8,0,17,10,C2D_Color32(242,91,112,255));
 C2D_DrawRectSolid(starx,stary,0,16,16,C2D_Color32(255,214,105,255));
 C2D_DrawRectSolid(starx+4,stary+4,0,8,8,C2D_Color32(255,249,178,255));
 for(int i=0;i<FOES;i++){
  C2D_DrawRectSolid(ex[i],ey[i],0,18,18,C2D_Color32(220,62,97,255));
  C2D_DrawRectSolid(ex[i]+4,ey[i]+4,0,4,4,C2D_Color32(28,29,48,255));
 }
 if(!iframes||tick%8<4){
  C2D_DrawRectSolid(x,y,0,20,20,C2D_Color32(85,223,155,255));
  C2D_DrawRectSolid(x+13,y+4,0,5,5,C2D_Color32(17,59,46,255));
 }
 if(!hp)C2D_DrawRectSolid(85,90,0,230,64,C2D_Color32(151,48,78,255));
 C3D_FrameEnd(0);
}
int main(int argc,char**argv){
 (void)argc;(void)argv;
 gfxInitDefault();
 consoleInit(GFX_BOTTOM,NULL);
 if(!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE)){
  gfxExit();return 1;
 }
 if(!C2D_Init(C2D_DEFAULT_MAX_OBJECTS)){
  C3D_Fini();gfxExit();return 2;
 }
 C2D_Prepare();
 C3D_RenderTarget*top=C2D_CreateScreenTarget(GFX_TOP,GFX_LEFT);
 if(!top){C2D_Fini();C3D_Fini();gfxExit();return 3;}
 reset();
 while(aptMainLoop()){
  hidScanInput();
  u32 held=hidKeysHeld(),pressed=hidKeysDown();
  if(pressed&KEY_START)break;
  if(pressed&KEY_X)reset();
  move(2*((held&KEY_DRIGHT)!=0)-2*((held&KEY_DLEFT)!=0),
       2*((held&KEY_DDOWN)!=0)-2*((held&KEY_DUP)!=0));
  if(held&KEY_TOUCH){
   touchPosition touch;hidTouchRead(&touch);
   /* Touchscreen is physically 320x240, project into top-screen 400x240. */
   int mx=touch.px*5/4,my=touch.py;
   if(abs(mx-starx)<25&&abs(my-stary)<25){
    starx=20+(int)(next_rng()%360);
    stary=18+(int)(next_rng()%200);
    score+=2;level=1+score/4;
   }
  }
  update();
  if(tick%30==0){
   printf("\x1b[1;1H DRAGON ORIGINAL 3DS                 ");
   printf("\x1b[3;1H Crystals: %d   Stage: %d      ",score,level);
   printf("\x1b[5;1H Lives: %d / 5                ",hp);
   printf("\x1b[7;1H D-PAD move / stylus collect ");
   printf("\x1b[9;1H X restart / START home      ");
   if(!hp)printf("\x1b[12;1H HATCHLING DOWN - X retry   ");
  }
  render(top);
 }
 C2D_Fini();C3D_Fini();gfxExit();
 return 0;
}
'''
THREEDS_MAKE=r'''# Native Nintendo 3DS devkitARM/libctru/citro2d homebrew.
ifeq ($(strip $(DEVKITPRO)),)
$(error DEVKITPRO required)
endif
ifeq ($(strip $(DEVKITARM)),)
$(error DEVKITARM required)
endif
include $(DEVKITARM)/3ds_rules
TARGET := dragon
ARCH := -march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft
CFLAGS := -O2 -Wall -Wextra -ffunction-sections $(ARCH) -I$(DEVKITPRO)/libctru/include -I$(DEVKITPRO)/portlibs/3ds/include
LDFLAGS := -specs=3dsx.specs $(ARCH)
LIBS := -lcitro2d -lcitro3d -lctru -lm
all: build/dragon.3dsx
build/main.o: src/main.c
	@mkdir -p build
	$(CC) $(CFLAGS) -c $< -o $@
build/dragon.elf: build/main.o
	$(CC) $(LDFLAGS) -o $@ $< -L$(DEVKITPRO)/portlibs/3ds/lib -L$(DEVKITPRO)/libctru/lib $(LIBS)
build/dragon.3dsx: build/dragon.elf
	3dsxtool $< $@
clean:
	rm -rf build
'''
def three_ds_source(seed:int)->dict[str,str]:
    n=_seed(seed)
    return {"src/main.c":THREEDS.replace("__SEED__",str(n)),
        "Makefile":THREEDS_MAKE,
        "README.port.md":"# Original Nintendo 3DS citro2d game\n"
        "Real ARM11/3DS top-screen C2D rectangles and bottom-console "
        "status; 3DS D-pad/stylus input, damage invulnerability, enemies, "
        "lives and leveling. Native homebrew 3dsx source only, not built/"
        "emulator-tested on devkitARM/libctru/citro2d. No Nintendo keys.\n"}
