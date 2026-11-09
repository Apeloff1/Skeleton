"""Original MOS 6510 / Commodore 64 native videogame source generator.

C64 screen RAM, VIC-II colors, CIA joystick port 2 and SID sound registers.
Not SDL, no browser and no machine-specific commercial assets.
"""
from __future__ import annotations

def commodore64_source(seed:int)->dict[str,str]:
    x=12+seed%20
    y=5+(seed//19)%15
    code=f"""\
/* Original Commodore 64 arcade cartridge-style exercise.
 * cc65 native machine code (.prg). VIC-II text graphics, CIA controls, SID.
 * Joystick in port 2: move the dragon to the sparkling crystal.
 */
#include <stdint.h>
#define SCREEN ((volatile unsigned char*)0x0400)
#define COLORS ((volatile unsigned char*)0xD800)
#define JOY2 (*(volatile unsigned char*)0xDC00)
#define BORDER (*(volatile unsigned char*)0xD020)
#define BG (*(volatile unsigned char*)0xD021)
#define SID ((volatile unsigned char*)0xD400)
static unsigned char x=2, y=3, goal_x={x},goal_y={y},score=0;
static void put(unsigned char px,unsigned char py,
                unsigned char character,unsigned char color){{
    unsigned int index=(unsigned int)py*40u+px;
    SCREEN[index]=character;
    COLORS[index]=color;
}}
static void tone(void){{
    /* Quick voiced chime. No sampled/copyrighted audio assets. */
    SID[0]=0xAA;SID[1]=0x20;
    SID[5]=0x09;SID[6]=0xF0;
    SID[4]=0x11;
}}
int main(void){{
    unsigned int i;
    volatile unsigned int delay;
    unsigned char pad,nx,ny;
    BORDER=6;BG=0;SID[24]=15;
    for(i=0;i<1000u;i++){{SCREEN[i]=32;COLORS[i]=1;}}
    for(i=0;i<40u;i++){{put((unsigned char)i,2,45,6);}}
    put(1,0,4,5);put(3,0,18,5);put(5,0,1,5);put(7,0,7,5);
    put(goal_x,goal_y,42,7);put(x,y,1,5);
    for(;;){{
        pad=JOY2;
        nx=x;ny=y;
        /* Active-low joystick 2 CIA bits: up 0, down 1, left 2, right 3. */
        if(!(pad&1)&&ny>3)ny--;
        if(!(pad&2)&&ny<24)ny++;
        if(!(pad&4)&&nx>0)nx--;
        if(!(pad&8)&&nx<39)nx++;
        if(nx!=x||ny!=y){{
            put(x,y,32,1);
            x=nx;y=ny;
            put(x,y,1,5);
        }}
        if(x==goal_x&&y==goal_y){{
            score++;
            tone();
            goal_x=(unsigned char)(4u+(score*13u+{seed % 1000}u)%32u);
            goal_y=(unsigned char)(4u+(score*7u+{(seed//9) % 1000}u)%19u);
            put(goal_x,goal_y,42,7);
            put(31,0,(unsigned char)(48u+score%10u),7);
        }}
        for(delay=0;delay<2400u;delay++){{ /* bounded slow loop */ }}
        SID[4]=0x10;
    }}
    return 0;
}}
"""
    return {
        "src/main.c":code,
        "Makefile":"""\
CL65 ?= cl65
.PHONY: all clean
all: build/dragon.prg
build/dragon.prg: src/main.c
\tmkdir -p build
\t$(CL65) -t c64 -O -o $@ $<
clean:
\trm -rf build
""",
    }
