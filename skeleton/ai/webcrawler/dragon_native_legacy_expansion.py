"""Original legacy native game implementations for materially different APIs.

All five outputs are SOURCE-ONLY until the corresponding cross compiler and
emulator verify them. Each backend has real controller/input, graphics/text
output and score/damage/restart state; no HTML or renamed desktop binary.
All characters and rules were authored for the Dragon homebrew practice lab.
"""
from __future__ import annotations

def _check_seed(seed:int)->int:
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**32:
        raise ValueError("native seed must be uint32")
    return seed or 1

APPLE_II=r'''/* Original Apple II 6502 game. cc65 ProDOS program via conio. */
#include <conio.h>
#include <stdint.h>
#define W 39
#define H 22
static unsigned int rng=__SEED__;
static unsigned char hero_x,hero_y,star_x,star_y,hp,score,stage;
static unsigned int random16(void) {
 rng^=rng<<7; rng^=rng>>9; rng^=rng<<8;return rng;
}
static void reset(void) {
 rng=__SEED__;hero_x=4;hero_y=5;star_x=23;star_y=12;
 hp=5;score=0;stage=1;
}
static void display(void) {
 unsigned char i;
 clrscr();
 gotoxy(0,0);cprintf("DRAGON APPLE II | score %u level %u",score,stage);
 for(i=0;i<hp;i++){gotoxy(i,1);cputc('*');}
 gotoxy(0,H);cputs("W A S D move / R restart / Q quit");
 gotoxy(star_x,star_y);cputc('+');
 gotoxy(hero_x,hero_y);cputc('D');
 if(!hp){gotoxy(7,10);cputs("GAME OVER - R to retry");}
}
int main(void) {
 char key;
 reset();
 while(1) {
  display();
  key=(char)cgetc();
  if(key=='q'||key=='Q')break;
  if(key=='r'||key=='R'){reset();continue;}
  if(!hp)continue;
  if((key=='a'||key=='A')&&hero_x>0)hero_x--;
  if((key=='d'||key=='D')&&hero_x<W)hero_x++;
  if((key=='w'||key=='W')&&hero_y>2)hero_y--;
  if((key=='s'||key=='S')&&hero_y<H-1)hero_y++;
  if(hero_x==star_x&&hero_y==star_y) {
   score++;stage=1+score/4;
   star_x=2+(unsigned char)(random16()%35);
   star_y=3+(unsigned char)(random16()%17);
   if(score%5==0&&hp<5)hp++;
  }
  if(stage>2&&((random16()&63)<(unsigned)stage))hp--;
 }
 clrscr();return 0;
}
'''
ZX_SPECTRUM=r'''/* Original 48K Spectrum: native Z80 keyboard/tape homebrew, z88dk. */
#include <conio.h>
#include <stdint.h>
#define W 29
#define H 19
static unsigned int rng=__SEED__;
static unsigned char x,y,star_x,star_y,hp,score,stage,tick;
static unsigned int rnd(void) {
 rng^=rng<<7;rng^=rng>>9;rng^=rng<<8;return rng;
}
static void reset(void) {
 rng=__SEED__;x=4;y=7;star_x=21;star_y=12;
 hp=5;score=0;stage=1;tick=0;
}
static void show(void) {
 clrscr();
 gotoxy(0,0);cprintf("DRAGON ZX48 S:%u LV:%u",score,stage);
 gotoxy(0,1);cprintf("HP:%u",hp);
 gotoxy(0,23);cputs("WASD move R retry Q quit");
 gotoxy(star_x,star_y);putch('*');
 gotoxy(x,y);putch('@');
 if(!hp){gotoxy(5,9);cputs("OUT OF LIVES");}
}
int main(void){
 char key;
 reset();
 while(1){
  show();key=(char)getch();
  if(key=='q'||key=='Q')break;
  if(key=='r'||key=='R'){reset();continue;}
  if(!hp)continue;
  if((key=='a'||key=='A')&&x>0)x--;
  if((key=='d'||key=='D')&&x<W)x++;
  if((key=='w'||key=='W')&&y>2)y--;
  if((key=='s'||key=='S')&&y<H)y++;
  if(x==star_x&&y==star_y){
   score++;stage=1+score/3;
   star_x=2+(unsigned char)(rnd()%26);
   star_y=4+(unsigned char)(rnd()%15);
   if(score%4==0&&hp<5)hp++;
  }
  tick++;
  if(stage>2 && (tick%25==0) && ((rnd()%8)<(stage/3)))hp--;
 }
 clrscr();return 0;
}
'''
DOS_8086=r'''/* Original DOS 8086 real-mode text game; OpenWatcom 16-bit. */
#include <stdio.h>
#include <conio.h>
#include <stdlib.h>
#define WIDTH 70
#define HEIGHT 22
static unsigned int seed=__SEED__;
static unsigned char x,y,star_x,star_y,enemy_x,enemy_y;
static int score,level,hp,tick;
static unsigned int rnd(void) {
 seed^=seed<<7;seed^=seed>>9;seed^=seed<<8;return seed;
}
static void reset_game(void){
 seed=__SEED__;x=6;y=7;star_x=32;star_y=12;
 enemy_x=58;enemy_y=17;score=0;level=1;hp=5;tick=0;
}
static void draw(void){
 clrscr();
 gotoxy(1,1);cprintf("DRAGON DOS 8086  Score:%d  Level:%d  Health:%d",score,level,hp);
 gotoxy(1,2);cputs("Move WASD, R restart, Q quit (16-bit real mode)");
 gotoxy(star_x,star_y);putch('*');
 gotoxy(enemy_x,enemy_y);putch('X');
 gotoxy(x,y);putch('@');
 if(!hp){gotoxy(27,11);cputs("DRAGON DOWN - R RETRY");}
}
int main(void){
 int key;
 reset_game();
 for(;;){
  draw();key=getch();
  if(key=='q'||key=='Q')break;
  if(key=='r'||key=='R'){reset_game();continue;}
  if(!hp)continue;
  if((key=='a'||key=='A')&&x>1)x--;
  if((key=='d'||key=='D')&&x<WIDTH)x++;
  if((key=='w'||key=='W')&&y>3)y--;
  if((key=='s'||key=='S')&&y<HEIGHT)y++;
  if(x==star_x&&y==star_y){
   score++;level=1+score/4;star_x=3+(unsigned char)(rnd()%65);
   star_y=4+(unsigned char)(rnd()%18);
  }
  if(level>2) {
   tick++;if(tick%(9-(level<8?level:7))==0){
    if(x>enemy_x)enemy_x++;else if(x<enemy_x)enemy_x--;
    if(y>enemy_y)enemy_y++;else if(y<enemy_y)enemy_y--;
   }
   if(x==enemy_x&&y==enemy_y){
    hp--;enemy_x=55;enemy_y=18;
   }
  }
 }
 clrscr();return 0;
}
'''
WIN95=r'''/* Win32/GDI original Dragon 95: no SDL, no browser, no DirectX. */
#define WINVER 0x0400
#define _WIN32_WINNT 0x0400
#include <windows.h>
#include <stdint.h>
#define W 640
#define H 480
typedef struct Game {int x,y,starx,stary,enemyx,enemyy,hp,score,level,tick;}Game;
static Game g;
static uint32_t rng=__SEED__u;
static int next_rand(int n) {
 rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
 return (int)(rng%(uint32_t)n);
}
static void reset(void){
 rng=__SEED__u;g.x=40;g.y=60;g.starx=320;g.stary=180;
 g.enemyx=500;g.enemyy=320;g.hp=5;g.score=0;g.level=1;g.tick=0;
}
static void paint(HDC dc) {
 HBRUSH sky=CreateSolidBrush(RGB(17,28,49));
 RECT frame={0,0,W,H};
 FillRect(dc,&frame,sky);DeleteObject(sky);
 HBRUSH dragon=CreateSolidBrush(RGB(78,214,152));
 HBRUSH gold=CreateSolidBrush(RGB(247,206,94));
 HBRUSH foe=CreateSolidBrush(RGB(231,77,97));
 RECT a={g.x,g.y,g.x+22,g.y+22};
 RECT b={g.starx,g.stary,g.starx+16,g.stary+16};
 RECT c={g.enemyx,g.enemyy,g.enemyx+21,g.enemyy+21};
 FillRect(dc,&a,dragon);FillRect(dc,&b,gold);FillRect(dc,&c,foe);
 DeleteObject(dragon);DeleteObject(gold);DeleteObject(foe);
 SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(252,226,151));
 char label[120];
 wsprintfA(label,"ORIGINAL DRAGON WIN95    Score: %d   Level: %d   HP: %d",g.score,g.level,g.hp);
 TextOutA(dc,12,12,label,lstrlenA(label));
 if(g.hp==0)TextOutA(dc,240,225,"GAME OVER - PRESS R",19);
 else TextOutA(dc,12,448,"ARROWS/WASD move, R restart, ESC quit",38);
}
static void tick(HWND hwnd){
 if(!g.hp)return;
 g.tick++;
 if(g.tick%4==0){
  int speed=1+(g.level>5);
  g.enemyx+=(g.x>g.enemyx?speed:-speed);
  g.enemyy+=(g.y>g.enemyy?speed:-speed);
 }
 if(g.x<g.enemyx+21 && g.x+22>g.enemyx &&
    g.y<g.enemyy+21 && g.y+22>g.enemyy) {
  g.hp--;g.enemyx=580;g.enemyy=410;
 }
 if(g.x<g.starx+16&&g.x+22>g.starx &&
    g.y<g.stary+16&&g.y+22>g.stary){
  g.score++;g.level=1+g.score/4;
  g.starx=15+next_rand(590);g.stary=45+next_rand(360);
  if(g.score%5==0&&g.hp<5)g.hp++;
 }
 InvalidateRect(hwnd,NULL,FALSE);
}
static LRESULT CALLBACK wndproc(HWND hwnd,UINT msg,WPARAM w,LPARAM l){
 switch(msg) {
  case WM_CREATE:SetTimer(hwnd,1,16,NULL);return 0;
  case WM_TIMER:tick(hwnd);return 0;
  case WM_KEYDOWN:
   if(w==VK_ESCAPE){DestroyWindow(hwnd);return 0;}
   if(w=='R'){reset();InvalidateRect(hwnd,NULL,FALSE);return 0;}
   if(g.hp){
    if(w==VK_LEFT||w=='A')g.x-=6;
    if(w==VK_RIGHT||w=='D')g.x+=6;
    if(w==VK_UP||w=='W')g.y-=6;
    if(w==VK_DOWN||w=='S')g.y+=6;
    if(g.x<0)g.x=0;if(g.x>W-22)g.x=W-22;
    if(g.y<32)g.y=32;if(g.y>H-44)g.y=H-44;
    InvalidateRect(hwnd,NULL,FALSE);
   }return 0;
  case WM_PAINT: {
   PAINTSTRUCT ps;HDC dc=BeginPaint(hwnd,&ps);
   paint(dc);EndPaint(hwnd,&ps);return 0;
  }
  case WM_DESTROY:KillTimer(hwnd,1);PostQuitMessage(0);return 0;
 }
 return DefWindowProcA(hwnd,msg,w,l);
}
int WINAPI WinMain(HINSTANCE h,HINSTANCE prev,LPSTR cmd,int show){
 WNDCLASSA wc={0};MSG msg;HWND hwnd;
 (void)prev;(void)cmd;
 reset();wc.hInstance=h;wc.lpfnWndProc=wndproc;
 wc.lpszClassName="OriginalDragonWin95";
 wc.hCursor=LoadCursor(NULL,IDC_ARROW);
 wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
 if(!RegisterClassA(&wc))return 1;
 hwnd=CreateWindowA(wc.lpszClassName,"Dragon Original Win95 GDI",
  WS_OVERLAPPEDWINDOW,CW_USEDEFAULT,CW_USEDEFAULT,W+16,H+48,
  NULL,NULL,h,NULL);
 if(!hwnd)return 2;
 ShowWindow(hwnd,show);UpdateWindow(hwnd);
 while(GetMessageA(&msg,NULL,0,0)>0){
  TranslateMessage(&msg);DispatchMessageA(&msg);
 }
 return (int)msg.wParam;
}
'''
ATARI_2600=r'''; Original Atari 2600 6507 / TIA cartridge; no vendor SDK.
; Console NTSC 262 scanlines: VSYNC 3, VBLANK 37, display 192, OVERSCAN 30.
; Press joystick UP/DOWN to move the original dragon square vertically.
; Bottom input fire restarts. Goal interaction changes sprite colour.
 processor 6502
 org $F000
VSYNC   = $00
VBLANK  = $01
WSYNC   = $02
NUSIZ0  = $04
COLUP0  = $06
COLUBK  = $09
CTRLPF  = $0A
PF0     = $0D
GRP0    = $1B
ENAM0   = $1D
SWCHA   = $0280
INPT4   = $3C
PlayerY = $80
StarY   = $81
Score   = $82
Tick    = $83
Start:
 sei
 cld
 ldx #$FF
 txs
 ldx #$7F
 lda #0
ClearRAM:
 sta $80,x
 dex
 bpl ClearRAM
 lda #__SEEDY__
 sta PlayerY
 lda #94
 sta StarY
 lda #$46
 sta COLUP0
 lda #$02
 sta NUSIZ0
Frame:
 lda #2
 sta VSYNC
 sta WSYNC
 sta WSYNC
 sta WSYNC
 lda #0
 sta VSYNC
 lda #2
 sta VBLANK
 ldx #37
BlankLines:
 sta WSYNC
 dex
 bne BlankLines
 lda #0
 sta VBLANK
 ; Read TIA/RIOT joystick (active low bits 4/5).
 lda SWCHA
 and #%00010000
 bne NoUp
 lda PlayerY
 cmp #1
 beq NoUp
 dec PlayerY
NoUp:
 lda SWCHA
 and #%00100000
 bne NoDown
 lda PlayerY
 cmp #180
 beq NoDown
 inc PlayerY
NoDown:
 ldx #0
Video:
 sta WSYNC
 txa
 sec
 sbc PlayerY
 cmp #9
 bcs NoDragon
 tay
 lda DragonSprite,y
 sta GRP0
 jmp SpriteDone
NoDragon:
 lda #0
 sta GRP0
SpriteDone:
 ; Goal hit in vertical slice increments original color-changing score.
 txa
 cmp StarY
 bne NextLine
 lda PlayerY
 sec
 sbc StarY
 cmp #9
 bcs NextLine
 inc Score
 lda Score
 and #$7F
 ora #$20
 sta COLUP0
NextLine:
 inx
 cpx #192
 bne Video
 lda #2
 sta VBLANK
 ldx #30
Overscan:
 sta WSYNC
 dex
 bne Overscan
 lda INPT4
 bmi Frame
 lda #0
 sta Score
 lda #__SEEDY__
 sta PlayerY
 jmp Frame
DragonSprite:
 .byte %00111100
 .byte %01111110
 .byte %11111111
 .byte %11011011
 .byte %11111111
 .byte %01111110
 .byte %00111100
 .byte %00011000
 org $FFFC
 .word Start
 .word Start
'''
def native_legacy_source(target_id:str,seed:int)->dict[str,str]:
    n=_check_seed(seed)
    if target_id=="apple_ii":
        files={"src/main.c":APPLE_II.replace("__SEED__",str(n&65535 or 1)),
               "Makefile":("CL65 ?= cl65\nall: build/dragon.bin\n"
                 "build/dragon.bin: src/main.c\n\tmkdir -p build\n"
                 "\t$(CL65) -t apple2 -O -o $@ $<\n"
                 "clean:\n\trm -rf build\n")}
    elif target_id=="zx_spectrum":
        files={"src/main.c":ZX_SPECTRUM.replace("__SEED__",str(n&65535 or 1)),
               "Makefile":("ZCC ?= zcc\nall: build/dragon.tap\n"
                 "build/dragon.tap: src/main.c\n\tmkdir -p build\n"
                 "\t$(ZCC) +zx -clib=ansi -create-app -o build/dragon $<\n"
                 "clean:\n\trm -rf build\n")}
    elif target_id=="dos_8086":
        files={"src/main.c":DOS_8086.replace("__SEED__",str(n&65535 or 1)),
               "Makefile":("WCL ?= wcl\nall: build/dragon.exe\n"
                 "build/dragon.exe: src/main.c\n\tmkdir -p build\n"
                 "\t$(WCL) -bt=dos -ms -fe=$@ $<\n"
                 "clean:\n\trm -rf build\n")}
    elif target_id=="windows_95":
        files={"src/main.c":WIN95.replace("__SEED__",str(n)),
               "Makefile":("MINGW32 ?= i686-w64-mingw32-gcc\n"
                 "all: build/dragon.exe\n"
                 "build/dragon.exe: src/main.c\n\tmkdir -p build\n"
                 "\t$(MINGW32) -std=c99 -Os -DWINVER=0x0400 -o $@ $< "
                 "-mwindows -lgdi32 -luser32\n"
                 "clean:\n\trm -rf build\n")}
    elif target_id=="atari_2600":
        files={"src/main.asm":ATARI_2600.replace("__SEEDY__",str(20+n%120)),
               "Makefile":("DASM ?= dasm\nall: build/dragon.bin\n"
                 "build/dragon.bin: src/main.asm\n\tmkdir -p build\n"
                 "\t$(DASM) $< -f3 -o$@\n"
                 "clean:\n\trm -rf build\n")}
    else:raise ValueError("unknown legacy native source target")
    files["README.port.md"]=(
        "# Original native "+target_id+" game\n\n"
        "This is a distinct native implementation, NOT an SDL/WebView "
        "or fake ROM wrapper. Compile with the indicated installed original "
        "cross compiler and emulator. The emitted files are source only: "
        "compilation, hardware frame timings, audio, real device playability, "
        "and compatibility across hardware revisions are unverified. "
        "No proprietary assets, bios, firmware or credentials included.\n"
    )
    return files
