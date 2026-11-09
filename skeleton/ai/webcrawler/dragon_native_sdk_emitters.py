"""Original native homebrew code for named SDK hardware generations.

These are SDK source templates, not proof of a successfully built or
hardware-tested ROM. SDKs/tools must be acquired separately and legally.
"""
from __future__ import annotations

def genesis_source(seed:int)->dict[str,str]:
    x=5+seed%16
    y=6+(seed//19)%12
    code=f"""\
/* Original Sega Mega Drive / Genesis game for SGDK.
   D-pad moves the hatchling text glyph onto the crystal. */
#include <genesis.h>
int main(bool hard) {{
    u16 x=4,y=4,goalx={x},goaly={y},score=0,frame=0;
    (void)hard;
    JOY_init();
    VDP_setScreenWidth320();
    VDP_drawText("DRAGON SGDK NATIVE LAB",5,1);
    VDP_drawText("D-PAD: REACH THE STAR",5,2);
    VDP_drawText("*",goalx,goaly);
    VDP_drawText("@",x,y);
    while(TRUE) {{
        const u16 pad=JOY_readJoypad(JOY_1);
        if((frame++ % 5)==0) {{
            const u16 beforeX=x,beforeY=y;
            if((pad&BUTTON_LEFT)&&x>0)x--;
            if((pad&BUTTON_RIGHT)&&x<39)x++;
            if((pad&BUTTON_UP)&&y>3)y--;
            if((pad&BUTTON_DOWN)&&y<27)y++;
            if(beforeX!=x||beforeY!=y) {{
                VDP_clearTextArea(beforeX,beforeY,1,1);
                VDP_drawText("@",x,y);
            }}
            if(x==goalx&&y==goaly) {{
                ++score;
                VDP_drawText("CRYSTAL FOUND!",5,24);
                VDP_clearTextArea(goalx,goaly,1,1);
                goalx=5+(score*13+{seed})%32;
                goaly=5+(score*7+{seed})%18;
                VDP_drawText("*",goalx,goaly);
            }}
        }}
        SYS_doVBlankProcess();
    }}
    return 0;
}}
"""
    return {"src/main.c":code,"Makefile":"""\
ifndef GDK
$(error SGDK root must be provided as GDK)
endif
include $(GDK)/makefile.gen
"""}

def gba_source(seed:int)->dict[str,str]:
    code=f"""\
/* Original Game Boy Advance ARM native MODE 3 bitmap mini-game.
   No browser, no Nintendo SDK assets. Compile with devkitARM/libgba. */
#include <stdint.h>
#define DISPLAY (*(volatile uint16_t*)0x04000000)
#define KEYS (*(volatile uint16_t*)0x04000130)
#define VCOUNT (*(volatile uint16_t*)0x04000006)
#define VRAM ((volatile uint16_t*)0x06000000)
#define RGB(r,g,b) ((r)|((g)<<5)|((b)<<10))
static void square(int x,int y,uint16_t color){{
    for(int yy=0;yy<8;yy++)for(int xx=0;xx<8;xx++){{
        int u=x+xx,v=y+yy;
        if(u>=0&&u<240&&v>=0&&v<160)VRAM[v*240+u]=color;
    }}
}}
int main(void){{
    int x=20,y=30,goalx={100+seed%125},goaly={20+(seed//13)%110},score=0;
    DISPLAY=0x0403; /* MODE3 | BG2_ON */
    for(int i=0;i<240*160;i++)VRAM[i]=RGB(2,5,9);
    square(goalx,goaly,RGB(31,28,2));
    square(x,y,RGB(8,31,18));
    for(;;){{
        while(VCOUNT>=160);
        while(VCOUNT<160);
        const uint16_t pressed=(uint16_t)(~KEYS);
        const int oldx=x,oldy=y;
        if((pressed&(1<<4))&&x<231)x++; /* RIGHT */
        if((pressed&(1<<5))&&x>1)x--;   /* LEFT */
        if((pressed&(1<<6))&&y>1)y--;   /* UP */
        if((pressed&(1<<7))&&y<151)y++; /* DOWN */
        if(x!=oldx||y!=oldy){{
            square(oldx,oldy,RGB(2,5,9));
            square(x,y,RGB(8,31,18));
        }}
        if(x>=goalx-7&&x<=goalx+7&&y>=goaly-7&&y<=goaly+7){{
            score++;
            square(goalx,goaly,RGB(2,5,9));
            goalx=12+(score*53+{seed})%210;
            goaly=12+(score*29+{seed})%135;
            square(goalx,goaly,RGB(31,28,2));
        }}
    }}
}}
"""
    # Requires devkitPro's gba.specs and gbafix utility; no claim of local build.
    makefile="""\
CC ?= arm-none-eabi-gcc
OBJCOPY ?= arm-none-eabi-objcopy
GBAFIX ?= gbafix
.PHONY: all clean
all: build/dragon.gba
build/dragon.elf: src/main.c
\tmkdir -p build
\t$(CC) -mthumb-interwork -mthumb -O2 -ffreestanding -specs=gba.specs -o $@ $<
build/dragon.gba: build/dragon.elf
\t$(OBJCOPY) -O binary $< $@
\t$(GBAFIX) $@
clean:
\trm -rf build
"""
    return {"src/main.c":code,"Makefile":makefile}

def ps1_source(seed:int)->dict[str,str]:
    # Uses common PSn00bSDK graphics and BIOS pad APIs. The toolchain must be
    # installed and the user must verify gamepad and display behavior.
    code=f"""\
/* Original Sony PlayStation 1 homebrew, PSn00bSDK build.
   Move a colored TILE with D-pad to touch the gold crystal. */
#include <stdint.h>
#include <psxgpu.h>
#include <psxetc.h>
#include <psxpad.h>
#include <psxapi.h>
static DISPENV disp[2];
static DRAWENV draw[2];
static unsigned char pad[2][34];
int main(void){{
    int db=0,x=30,y=60,goalx={120+(seed%120)},goaly={70+(seed//23)%100};
    ResetGraph(0);
    SetDefDispEnv(&disp[0],0,0,320,240);
    SetDefDrawEnv(&draw[0],0,240,320,240);
    SetDefDispEnv(&disp[1],0,240,320,240);
    SetDefDrawEnv(&draw[1],0,0,320,240);
    setRGB0(&draw[0],16,24,40);
    setRGB0(&draw[1],16,24,40);
    draw[0].isbg=draw[1].isbg=1;
    InitPAD(pad[0],34,pad[1],34);
    StartPAD();
    SetDispMask(1);
    for(;;){{
        uint16_t keys=(uint16_t)~((pad[0][2]<<8)|pad[0][3]);
        /* BIOS packet: active-low bits for D-pad directions */
        if((keys&0x0080)&&x>0)x--;
        if((keys&0x0020)&&x<296)x++;
        if((keys&0x0010)&&y>0)y--;
        if((keys&0x0040)&&y<216)y++;
        if(x>=goalx-20&&x<=goalx+20&&y>=goaly-20&&y<=goaly+20){{
            goalx=45+(goalx*3+{seed})%230;
            goaly=30+(goaly*3+{seed})%165;
        }}
        DrawSync(0);
        VSync(0);
        PutDispEnv(&disp[db]);
        PutDrawEnv(&draw[db]);
        TILE hero,star;
        setTile(&hero);setXY0(&hero,x,y);setWH(&hero,20,20);setRGB0(&hero,90,220,133);
        setTile(&star);setXY0(&star,goalx,goaly);setWH(&star,16,16);setRGB0(&star,240,202,74);
        DrawPrim(&star);
        DrawPrim(&hero);
        db^=1;
    }}
    return 0;
}}
"""
    cmake="""\
cmake_minimum_required(VERSION 3.18)
project(DragonPS1 C)
psn00bsdk_add_executable(dragon GPREL src/main.c)
"""
    return {"src/main.c":code,"CMakeLists.txt":cmake}

def xbox_original_source(seed:int,style:str)->dict[str,str]:
    # nxdk provides SDL2; use existing 2D game logic but add actual gamepad
    # movement (not keyboard-only, which would make an Xbox game unplayable).
    from .dragon_native_projects import _desktop
    desktop=_desktop(seed,style)
    source=desktop["src/main.c"]
    source=source.replace(
        '    SDL_RenderSetLogicalSize(r,W,H);',
        '''    SDL_RenderSetLogicalSize(r,W,H);
    SDL_GameController*pad=NULL;
    for(int i=0;i<SDL_NumJoysticks();i++){
        if(SDL_IsGameController(i)){pad=SDL_GameControllerOpen(i);break;}
    }''')
    source=source.replace(
        '''        x+=4.0f*horiz;''',
        '''        if(pad){
            const float px=SDL_GameControllerGetAxis(pad,SDL_CONTROLLER_AXIS_LEFTX)/32768.0f;
            const float py=SDL_GameControllerGetAxis(pad,SDL_CONTROLLER_AXIS_LEFTY)/32768.0f;
            horiz+=px;
            vert+=py;
        }
        x+=4.0f*horiz;''')
    source=source.replace(
        'SDL_DestroyRenderer(r);SDL_DestroyWindow(w);SDL_Quit();',
        'if(pad)SDL_GameControllerClose(pad);SDL_DestroyRenderer(r);SDL_DestroyWindow(w);SDL_Quit();')
    makefile="""\
ifndef NXDK_DIR
$(error Provide NXDK_DIR pointing to installed original-Xbox nxdk)
endif
XBE_TITLE = DragonNative
NXDK_SDL = y
SRCS = $(CURDIR)/src/main.c
include $(NXDK_DIR)/Makefile
"""
    return {"src/main.c":source,"Makefile":makefile}
