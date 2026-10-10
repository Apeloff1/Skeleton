"""Native, original console/PC game projects. Source, never fake ROM binaries."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
import json
import re
from .dragon_game_mechanics import Mechanic
from .dragon_native_targets import demand_target, STYLES

EMITTERS=frozenset({"game_boy","game_boy_color","nes","dos_vga","master_system","game_gear","snes","commodore_64","genesis","game_boy_advance","nintendo_64","nintendo_ds","psp","ps1","xbox_original","pc_linux","pc_windows","pc_macos","steam_deck"})

@dataclass(frozen=True)
class NativeProject:
    project_id:str
    target_id:str
    style:str
    title:str
    status:str
    toolchain:str
    output:str
    files:dict[str,str]
    digest:str
    supported_mechanics:tuple[str,...]
    deferred_mechanics:tuple[str,...]

def digest(v:object)->str:
    return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def _gameboy(seed:int)->dict[str,str]:
    x=90+seed%55
    y=65+(seed//17)%65
    source=f"""\
; ORIGINAL Nintendo Game Boy DMG homebrew. Assemble with RGBDS.
; Move smiling hatchling with D-pad and touch star to change color palette.
DEF rJOYP EQU $FF00
DEF rLCDC EQU $FF40
DEF rLY EQU $FF44
DEF rOBP0 EQU $FF48
DEF OAM EQU $FE00
DEF VRAM EQU $8000
DEF GOAL_X EQU {x}
DEF GOAL_Y EQU {y}
SECTION "Entry", ROM0[$100]
    jp Start
    ds $0150 - @, 0
SECTION "Game", ROM0[$150]
Start:
    di
    ld sp, $FFFE
.waitLCD:
    ldh a, [rLY]
    cp 144
    jr c, .waitLCD
    xor a
    ldh [rLCDC], a
    ld hl, OAM
    ld b, 160
.clear:
    ld [hli], a
    dec b
    jr nz, .clear
    ld hl, VRAM
    ld de, Tiles
    ld b, TilesEnd-Tiles
.tiles:
    ld a, [de]
    ld [hli], a
    inc de
    dec b
    jr nz, .tiles
    ld a, 48
    ld [PlayerX], a
    ld a, 63
    ld [PlayerY], a
    ld a, $E4
    ldh [rOBP0], a
    ld a, $82
    ldh [rLCDC], a
.loop:
    call WaitFrame
    call Input
    call Sprites
    jr .loop
WaitFrame:
    ldh a, [rLY]
    cp 144
    jr nc, WaitFrame
.wait:
    ldh a, [rLY]
    cp 144
    jr c, .wait
    ret
Input:
    ld a, $20
    ldh [rJOYP], a
    ldh a, [rJOYP]
    cpl
    and $0F
    ld b, a
    bit 0,b
    jr z,.noR
    ld hl,PlayerX
    ld a,[hl]
    cp 158
    jr nc,.noR
    inc [hl]
.noR:
    bit 1,b
    jr z,.noL
    ld hl,PlayerX
    ld a,[hl]
    cp 9
    jr c,.noL
    dec [hl]
.noL:
    bit 2,b
    jr z,.noU
    ld hl,PlayerY
    ld a,[hl]
    cp 17
    jr c,.noU
    dec [hl]
.noU:
    bit 3,b
    jr z,.noD
    ld hl,PlayerY
    ld a,[hl]
    cp 151
    jr nc,.noD
    inc [hl]
.noD:
    ld a,$30
    ldh [rJOYP],a
    ret
Sprites:
    ld a,[PlayerY]
    ld [OAM],a
    ld a,[PlayerX]
    ld [OAM+1],a
    xor a
    ld [OAM+2],a
    ld [OAM+3],a
    ld a,GOAL_Y
    ld [OAM+4],a
    ld a,GOAL_X
    ld [OAM+5],a
    ld a,1
    ld [OAM+6],a
    xor a
    ld [OAM+7],a
    ld a,[PlayerX]
    cp GOAL_X
    jr nz,.notWin
    ld a,[PlayerY]
    cp GOAL_Y
    jr nz,.notWin
    ld a,$1B
    ldh [rOBP0],a
.notWin:
    ret
Tiles:
    db $3C,$3C,$42,$42,$A5,$A5,$81,$81
    db $A5,$A5,$99,$99,$42,$42,$3C,$3C
    db $18,$18,$3C,$3C,$7E,$7E,$FF,$FF
    db $7E,$7E,$3C,$3C,$18,$18,$00,$00
TilesEnd:
SECTION "Variables", WRAM0
PlayerX: ds 1
PlayerY: ds 1
"""
    return {"src/main.asm":source,"Makefile":"""\
RGBASM ?= rgbasm
RGBLINK ?= rgblink
RGBFIX ?= rgbfix
.PHONY: all clean
all: build/dragon.gb
build/dragon.o: src/main.asm
\tmkdir -p build
\t$(RGBASM) -o $@ $<
build/dragon.gb: build/dragon.o
\t$(RGBLINK) -o $@ $<
\t$(RGBFIX) -v -p 0 -t DRAGONLAB $@
clean:
\trm -rf build
"""}

def _nes(seed:int)->dict[str,str]:
    # iNES NROM-256, 32 KiB PRG, 8 KiB CHR; 6502 source for ca65/ld65.
    source=f"""\
.segment "HEADER"
.byte "NES", $1A, 2, 1, 0, 0
.res 8, 0
.segment "CODE"
Reset:
    sei
    cld
    ldx #$40
    stx $4017
    ldx #$FF
    txs
    inx
    stx $2000
    stx $2001
    stx $4010
wait1:
    bit $2002
    bpl wait1
    ldx #0
    lda #$FF
clearOAM:
    sta $0200,x
    inx
    bne clearOAM
    lda #{80+(seed//19)%30}
    sta $0200
    lda #0
    sta $0201
    sta $0202
    lda #{50+seed%35}
    sta $0203
    lda #112
    sta $0204
    lda #1
    sta $0205
    lda #0
    sta $0206
    lda #178
    sta $0207
wait2:
    bit $2002
    bpl wait2
    lda #$3F
    sta $2006
    lda #0
    sta $2006
    ldx #0
palette:
    lda Colors,x
    sta $2007
    inx
    cpx #32
    bne palette
    lda #%00010000
    sta $2001
Loop:
    bit $2002
    bpl Loop
    lda #0
    sta $2003
    lda #$02
    sta $4014
    jsr PollPad
    lda $0203
    cmp #178
    bne continue
    lda $0200
    cmp #112
    bne continue
    lda #1
    sta $0202
continue:
notVBlank:
    bit $2002
    bmi notVBlank
    jmp Loop
PollPad:
    lda #1
    sta $4016
    lda #0
    sta $4016
    ldx #4
skipAB:
    lda $4016
    dex
    bne skipAB
    lda $4016
    and #1
    beq upDone
    dec $0200
upDone:
    lda $4016
    and #1
    beq downDone
    inc $0200
downDone:
    lda $4016
    and #1
    beq leftDone
    dec $0203
leftDone:
    lda $4016
    and #1
    beq rightDone
    inc $0203
rightDone:
    rts
Colors:
.byte $0F,$30,$16,$26,$0F,$30,$10,$20,$0F,$30,$00,$10,$0F,$30,$06,$16
.byte $0F,$30,$16,$26,$0F,$30,$21,$11,$0F,$30,$06,$16,$0F,$30,$16,$26
NMI: rti
IRQ: rti
.segment "VECTORS"
.addr NMI, Reset, IRQ
.segment "CHARS"
.byte $3C,$42,$A5,$81,$A5,$99,$42,$3C,$3C,$42,$A5,$81,$A5,$99,$42,$3C
.byte $18,$3C,$7E,$FF,$7E,$3C,$18,$00,$18,$3C,$7E,$FF,$7E,$3C,$18,$00
.res $2000-32,0
"""
    cfg="""\
MEMORY {
 HEADER: start=$0000, size=$0010, type=ro, file=%O;
 ZP: start=$0000, size=$0100, type=rw;
 RAM: start=$0200, size=$0600, type=rw;
 PRG: start=$8000, size=$7FFA, type=ro, file=%O, fill=yes;
 VEC: start=$FFFA, size=$0006, type=ro, file=%O;
 CHR: start=$0000, size=$2000, type=ro, file=%O, fill=yes;
}
SEGMENTS {
 HEADER: load=HEADER, type=ro;
 ZEROPAGE: load=ZP, type=zp;
 BSS: load=RAM, type=bss;
 CODE: load=PRG, type=ro;
 VECTORS: load=VEC, type=ro;
 CHARS: load=CHR, type=ro;
}
"""
    makefile="""\
CA65 ?= ca65
LD65 ?= ld65
.PHONY: all clean
all: build/dragon.nes
build/dragon.o: src/main.s
\tmkdir -p build
\t$(CA65) -o $@ $<
build/dragon.nes: build/dragon.o nes.cfg
\t$(LD65) -C nes.cfg -o $@ $<
clean:
\trm -rf build
"""
    return {"src/main.s":source,"nes.cfg":cfg,"Makefile":makefile}

def _dos(seed:int)->dict[str,str]:
    src=r"""/* Original DJGPP DOS VGA game, 386+ and DPMI extender.
   WASD moves the green avatar; collect gold blocks, Q exits. */
#include <dpmi.h>
#include <sys/farptr.h>
#include <conio.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include <stdlib.h>
#define W 320
#define H 200
static unsigned char pixels[W*H];
static void mode(unsigned char m) {
    __dpmi_regs r; memset(&r,0,sizeof(r));
    r.h.ah=0;r.h.al=m;__dpmi_int(0x10,&r);
}
static void square(int x,int y,int d,unsigned char c) {
    for(int yy=y;yy<y+d;yy++)if(yy>=0&&yy<H)
        for(int xx=x;xx<x+d;xx++)if(xx>=0&&xx<W)pixels[yy*W+xx]=c;
}
int main(void) {
    int x=30,y=60,goalX=GOAL_X,goalY=GOAL_Y,score=0;
    mode(0x13);
    for(;;) {
        int key=kbhit()?tolower(getch()):0;
        if(key=='q'||key==27)break;
        if(key=='a'&&x>2)x-=3;
        if(key=='d'&&x<W-14)x+=3;
        if(key=='w'&&y>2)y-=3;
        if(key=='s'&&y<H-14)y+=3;
        if(abs(x-goalX)<12&&abs(y-goalY)<12){
            score++;goalX=20+(score*53)%270;goalY=15+(score*61)%170;
        }
        memset(pixels,0,sizeof(pixels));
        square(goalX,goalY,10,14);
        square(x,y,11,10);
        for(int i=0;i<score&&i<30;i++)square(3+i*10,2,6,14);
        dosmemput(pixels,sizeof(pixels),0xA0000);
        usleep(17000);
    }
    mode(3);
    printf("Crystals: %d\n",score);
    return 0;
}
""".replace("GOAL_X",str(170+seed%90)).replace("GOAL_Y",str(30+(seed//31)%110))
    return {"src/main.c":src,"Makefile":"""\
CC ?= i586-pc-msdosdjgpp-gcc
.PHONY: all clean
all: build/dragon.exe
build/dragon.exe: src/main.c
\tmkdir -p build
\t$(CC) -O2 -Wall -o $@ $<
clean:
\trm -rf build
"""}

def _desktop(seed:int,style:str)->dict[str,str]:
    mode=1 if style in ("side_scrolling_platformer","metroidvania","puzzle_platformer") else 0
    src=r"""/* Original native SDL2 desktop game. No JavaScript or browser. */
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#define W 800
#define H 480
static void block(SDL_Renderer*r,int x,int y,int w,int h,int red,int green,int blue){
    SDL_Rect box={x,y,w,h};
    SDL_SetRenderDrawColor(r,(Uint8)red,(Uint8)green,(Uint8)blue,255);
    SDL_RenderFillRect(r,&box);
}
int main(int argc,char **argv){
    (void)argc;(void)argv;
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS|SDL_INIT_GAMECONTROLLER)!=0)return 1;
    SDL_Window*w=SDL_CreateWindow("Dragon Native Adventure",SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,W,H,SDL_WINDOW_SHOWN|SDL_WINDOW_RESIZABLE);
    if(!w){SDL_Quit();return 2;}
    SDL_Renderer*r=SDL_CreateRenderer(w,-1,SDL_RENDERER_ACCELERATED|SDL_RENDERER_PRESENTVSYNC);
    if(!r)r=SDL_CreateRenderer(w,-1,SDL_RENDERER_SOFTWARE);
    if(!r){SDL_DestroyWindow(w);SDL_Quit();return 3;}
    SDL_RenderSetLogicalSize(r,W,H);
    float x=40,y=220,vy=0;
    int cx=500+SEED%210,cy=90+(SEED/13)%310,score=0,alive=1;
    Uint32 last=SDL_GetTicks();
    while(alive){
        SDL_Event e;
        while(SDL_PollEvent(&e)){
            if(e.type==SDL_QUIT)alive=0;
            if(e.type==SDL_KEYDOWN&&e.key.keysym.sym==SDLK_ESCAPE)alive=0;
        }
        Uint32 now=SDL_GetTicks();
        if(now-last<16){SDL_Delay(1);continue;}
        last=now;
        const Uint8*k=SDL_GetKeyboardState(NULL);
        float horiz=(float)(k[SDL_SCANCODE_D]||k[SDL_SCANCODE_RIGHT])
                   -(float)(k[SDL_SCANCODE_A]||k[SDL_SCANCODE_LEFT]);
        float vert=(float)(k[SDL_SCANCODE_S]||k[SDL_SCANCODE_DOWN])
                  -(float)(k[SDL_SCANCODE_W]||k[SDL_SCANCODE_UP]);
        x+=4.0f*horiz;
        if(GAME_MODE){
            vy+=0.45f;
            if((k[SDL_SCANCODE_SPACE]||k[SDL_SCANCODE_UP])&&y>=411)vy=-10.5f;
            y+=vy;
            if(y>411){y=411;vy=0;}
        }else y+=4.0f*vert;
        if(x<0)x=0;if(x>W-22)x=W-22;
        if(y<0)y=0;if(y>H-22)y=H-22;
        if(fabsf(x-cx)<22&&fabsf(y-cy)<22){
            score++;cx=40+(score*109+SEED)%715;cy=40+(score*67+SEED)%385;
            SDL_Log("Dragon collected %d crystals",score);
        }
        SDL_SetRenderDrawColor(r,18,30,44,255);SDL_RenderClear(r);
        for(int j=0;j<50;j++)block(r,(j*97+SEED)%W,(j*37)%H,3,3,35,64,85);
        if(GAME_MODE)block(r,0,433,W,47,64,103,78);
        block(r,cx,cy,18,18,255,210,95);
        block(r,(int)x,(int)y,22,22,105,205,135);
        block(r,(int)x+14,(int)y+7,3,3,22,32,40);
        for(int j=0;j<score&&j<35;j++)block(r,5+j*20,8,12,8,255,210,95);
        SDL_RenderPresent(r);
    }
    SDL_DestroyRenderer(r);SDL_DestroyWindow(w);SDL_Quit();
    return 0;
}
""".replace("SEED",str(seed)).replace("GAME_MODE",str(mode))
    cmake="""\
cmake_minimum_required(VERSION 3.16)
project(DragonNativeGame C)
set(CMAKE_C_STANDARD 99)
find_package(SDL2 REQUIRED)
add_executable(dragon_game src/main.c)
if(TARGET SDL2::SDL2)
  target_link_libraries(dragon_game PRIVATE SDL2::SDL2)
else()
  target_include_directories(dragon_game PRIVATE ${SDL2_INCLUDE_DIRS})
  target_link_libraries(dragon_game PRIVATE ${SDL2_LIBRARIES})
endif()
if(TARGET SDL2::SDL2main)
  target_link_libraries(dragon_game PRIVATE SDL2::SDL2main)
endif()
if(NOT MSVC)
  target_link_libraries(dragon_game PRIVATE m)
endif()
"""
    return {"src/main.c":src,"CMakeLists.txt":cmake}

def render_native_project(*,title:str,target_id:str,style:str,
                          candidate_id:str,mechanics:tuple[Mechanic,...],
                          authorized:bool,design=None)->NativeProject:
    if not authorized:raise PermissionError("native game build requires authorization")
    target=demand_target(target_id)
    if target_id not in EMITTERS:
        if target.status=="licensed_sdk":
            raise PermissionError("licensed console SDK required; no fake export")
        raise ValueError("hardware emitter not implemented")
    if style not in STYLES:raise ValueError("unknown game style")
    # Console renderers below are real CPU/SDK code, but currently provide
    # ONLY a collectible chase; do not advertise an unimplemented RPG/RTS.
    if target_id not in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        allowed = ("arcade_score_attack","side_scrolling_platformer") if target_id=="game_boy" else ("arcade_score_attack",)
        if style not in allowed:
            raise ValueError("target has not implemented the requested gameplay style")
    if not isinstance(title,str) or not 2<=len(title.strip())<=80:
        raise ValueError("invalid title")
    if not isinstance(candidate_id,str) or not re.fullmatch("[a-f0-9]{64}",candidate_id):
        raise ValueError("canonical source candidate digest required")
    if not mechanics or len(mechanics)>16 or len(set(mechanics))!=len(mechanics) or not all(
        isinstance(m,Mechanic) for m in mechanics):
        raise ValueError("invalid mechanic inventory")
    if design is not None:
        from .dragon_game_design import GameDesign
        if not isinstance(design,GameDesign) or (
            design.target!=target_id or design.genre!=style or design.title!=title
        ):
            raise ValueError("game design must match title, target and genre")
    # Research titles never become executable source or build script literals.
    clean=" ".join(re.findall("[A-Za-z0-9]+",title)[:8])[:42] or "Dragon Native"
    seed=(design.seed if design is not None else int(
        digest([candidate_id,target_id,style])[:8],16))
    if target_id=="game_boy" and style=="side_scrolling_platformer":
        from .dragon_gb_platformer import gb_platformer_source
        files=gb_platformer_source(seed)
    elif target_id=="game_boy_color":
        from .dragon_native_gbc import color_game_boy
        files=color_game_boy(_gameboy(seed)["src/main.asm"],_gameboy(seed)["Makefile"],seed)
    elif target_id in ("master_system","game_gear"):
        from .dragon_native_sms import sms_source
        files=sms_source(seed,game_gear=(target_id=="game_gear"))
    elif target_id=="snes":
        from .dragon_native_snes import snes_source
        files=snes_source(seed)
    elif target_id in ("nintendo_64","nintendo_ds","psp"):
        from .dragon_native_3d_era import n64_source,ds_source,psp_source
        files=(n64_source(seed) if target_id=="nintendo_64" else
               ds_source(seed) if target_id=="nintendo_ds" else psp_source(seed))
    elif target_id=="commodore_64":
        from .dragon_native_c64 import commodore64_source
        files=commodore64_source(seed)
    elif target_id in ("genesis","game_boy_advance","ps1","xbox_original"):
        from .dragon_native_sdk_emitters import (
            genesis_source,gba_source,ps1_source,xbox_original_source,
        )
        files=(
            genesis_source(seed) if target_id=="genesis" else
            gba_source(seed) if target_id=="game_boy_advance" else
            ps1_source(seed) if target_id=="ps1" else
            xbox_original_source(seed,style)
        )
    elif target_id in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        from .dragon_game_blueprints import GENRES, campaign_dict
        from .dragon_game_fitness import choose_campaign,selection_report
        from .dragon_native_arcade_runtime import render_sdl_campaign
        if style not in GENRES and style not in ("rhythm_game","fixed_screen_puzzle"):
            raise ValueError("gameplay genre does not yet have an implemented native mode")
        if style=="fixed_screen_puzzle":
            from .dragon_native_puzzle import emit_native_puzzle
            files=emit_native_puzzle(
                seed=seed,stages=design.stages if design is not None else 4,
                difficulty=design.difficulty if design is not None else 4)
            if design is not None:
                from .dragon_game_design import design_manifest
                files["dragon-game-design.json"]=json.dumps(
                    design_manifest(design),sort_keys=True,indent=2)+"\n"
        elif style=="rhythm_game":
            from .dragon_native_rhythm import render_rhythm
            songs=design.stages if design is not None else 4
            files=render_rhythm(seed=seed,songs=songs,
                 difficulty=design.difficulty if design is not None else 4)
            if design is not None:
                from .dragon_game_design import design_manifest
                files["dragon-game-design.json"]=json.dumps(
                    design_manifest(design),sort_keys=True,indent=2)+"\n"
            files["dragon-rhythm-production.json"]=json.dumps({
                "schema":"skeleton.ai.dragon.native_rhythm_production.v1",
                "songs":songs,"notes_per_song":64,
                "runtime":"fixed_60hz_native_sdl2",
                "visual_or_player_verified":False
            },sort_keys=True,indent=2)+"\n"
        else:
            palette=(
                "modern_neon" if style in ("arcade_score_attack","bullet_hell") else
                "dmg_green" if style in ("roguelike","survival_horror") else
                "vga_dusk" if style in ("top_down_adventure","educational") else
                "crt_arcade" if style in ("racing","run_and_gun") else "handheld"
            )
            if design is not None:palette=design.palette
            selection=choose_campaign(
                style=style,seed=seed,
                stages=design.stages if design is not None else 4,
                palette=palette,budget=design.candidates if design is not None else 8,
                difficulty=design.difficulty if design is not None else 4)
            campaign=selection.chosen
            from .dragon_playtest_planner import plan_campaign,agent_report
            abstract_plan=plan_campaign(campaign)
            if style in ("first_person_shooter","immersive_sim"):
                from .dragon_native_raycaster import render_raycaster
                files=render_raycaster(
                    campaign,difficulty=design.difficulty if design is not None else 4,
                    theme=design.quest_theme if design is not None else "ancient_ruins")
            elif style=="turn_based_rpg":
                from .dragon_native_turn_rpg import render_rpg
                files=render_rpg(campaign)
            else:
                files=render_sdl_campaign(
                    campaign,hero=design.hero if design is not None else "hatchling",
                    theme=design.quest_theme if design is not None else "ancient_ruins",
                    difficulty=design.difficulty if design is not None else 4)
            files["dragon-playtest-plan.json"]=json.dumps(
                agent_report(abstract_plan),sort_keys=True,indent=2)+"\n"
            files["dragon-generator-evaluation.json"]=json.dumps(
                selection_report(selection),sort_keys=True,indent=2)+"\n"
            files["dragon-campaign.json"]=json.dumps(
                campaign_dict(campaign),sort_keys=True,indent=2)+"\n"
            if design is not None:
                from .dragon_game_design import design_manifest
                files["dragon-game-design.json"]=json.dumps(
                    design_manifest(design),sort_keys=True,indent=2)+"\n"
    else:
        files=(_gameboy(seed) if target_id=="game_boy" else
               _nes(seed) if target_id=="nes" else
               _dos(seed) if target_id=="dos_vga" else _desktop(seed,style))
    if target_id in ("game_boy","game_boy_color","nes") and not (
        target_id=="game_boy" and style=="side_scrolling_platformer"
    ):
        from .dragon_retro_assets import (
            asset_tiles,enrich_gb_asm,enrich_nes_asm,
        )
        if target_id in ("game_boy","game_boy_color"):
            files["src/main.asm"]=enrich_gb_asm(files["src/main.asm"])
        else:
            files["src/main.s"]=enrich_nes_asm(files["src/main.s"])
        files["dragon-pixel-art.json"]=json.dumps({
            "schema":"skeleton.ai.dragon.original_pixel_art.v1",
            "sprites":[{"id":sprite.name,"fingerprint":sprite.digest}
                       for sprite in asset_tiles()],
            "encoding": "interleaved_2bpp" if target_id in ("game_boy","game_boy_color")
                        else "nes_planar_2bpp",
        },sort_keys=True,indent=2)+"\n"
    if target_id=="game_boy_advance":
        from .dragon_hw_graphics import atlas_header,source_manifest
        files["include/dragon_original_tiles.h"]=atlas_header("gba_nibbles")
        files["dragon-hardware-art.json"]=json.dumps(
            source_manifest("gba_nibbles"),sort_keys=True,indent=2)+"\n"
        source=files["src/main.c"]
        anchor="#include <stdint.h>"
        if anchor not in source:raise ValueError("GBA native source include anchor missing")
        source=source.replace(anchor,anchor+'\n#include "dragon_original_tiles.h"',1)
        anchor2="int main(void){"
        drawer="""static void draw_dragon(int x,int y){
    static const uint16_t ink[4]={RGB(2,5,9),RGB(8,18,10),
                                   RGB(8,31,18),RGB(31,30,15)};
    for(int yy=0;yy<8;yy++)for(int xx=0;xx<8;xx++){
        unsigned char packed=dragon_native_tiles[yy*4+xx/2];
        unsigned char index=(xx&1)?(packed>>4):(packed&15);
        int u=x+xx,v=y+yy;
        if(u>=0&&u<240&&v>=0&&v<160)VRAM[v*240+u]=ink[index&3];
    }
}
"""
        if anchor2 not in source:raise ValueError("GBA native source main unavailable")
        source=source.replace(anchor2,drawer+anchor2,1)
        source=source.replace("square(x,y,RGB(8,31,18));","draw_dragon(x,y);")
        files["src/main.c"]=source
        files["Makefile"]=files["Makefile"].replace("-specs=gba.specs","-Iinclude -specs=gba.specs")
    if target_id in ("snes","genesis"):
        from .dragon_hw_graphics import atlas_header,source_manifest
        layout="snes_planar4" if target_id=="snes" else "genesis_nibbles"
        files["include/dragon_original_tiles.h"]=atlas_header(layout)
        files["dragon-hardware-art.json"]=json.dumps(
            source_manifest(layout),sort_keys=True,indent=2)+"\n"
    if target_id in ("master_system","game_gear"):
        from .dragon_hw_graphics import source_manifest
        files["dragon-hardware-art.json"]=json.dumps(
            source_manifest("sega_vdp_planar4"),sort_keys=True,indent=2)+"\n"
    if target_id in ("game_boy","game_boy_color"):
        from .dragon_gb_sound import enrich_native_gb_sound
        files["src/main.asm"]=enrich_native_gb_sound(
            files["src/main.asm"],
            scrolling=(target_id=="game_boy" and style=="side_scrolling_platformer"))
    # Physically install original 2bpp actor/theme sprite tiles into the
    # ROM source before canonical hardware budgeting. Existing frame/tile
    # IDs and game logic remain stable; no proprietary assets are involved.
    if design is not None and target_id in ("game_boy", "game_boy_color", "nes"):
        from .dragon_native_artforge import make_art, apply_original_art
        art, tiles = make_art(
            hero=design.hero, theme=design.quest_theme,
            palette=design.palette, seed=design.seed, target=target_id,
        )
        files = apply_original_art(files, art=art, tiles=tiles, style=style)
    if any(PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts for p in files):
        raise ValueError("unsafe generated path")
    if any(len(v.encode())>120_000 for v in files.values()):
        raise ValueError("native project source exceeds budget")
    from .dragon_hardware_budget import analyze_project_budget
    from dataclasses import asdict as _asdict
    hardware=_asdict(analyze_project_budget(target_id,files))
    files["dragon-hardware-budget.json"]=json.dumps(
        hardware,sort_keys=True,indent=2)+"\n"
    implemented={Mechanic.MOVEMENT,Mechanic.EXPLORATION}
    if target_id in ("pc_linux","pc_windows","pc_macos","steam_deck","xbox_original"):
        implemented|={Mechanic.PLATFORMING,Mechanic.PHYSICS}
    supported=tuple(sorted(m.value for m in mechanics if m in implemented))
    deferred=tuple(sorted(m.value for m in mechanics if m not in implemented))
    files["README.md"]=(
        "# "+clean+" — "+target.family+" native game\n\n"
        "This is original HOME BREW source, not a commercial ROM or an HTML game.\n"
        "Style goal: "+style+". Hardware: "+target.cpu+" / "+target.graphics+".\n"
        "Required toolchain: "+target.toolchain+". Expected extension: ."+target.output+".\n"
        "Build: make (RGBDS, cc65 or DJGPP), or cmake -S . -B build then cmake --build build (SDL2 PCs).\n"
        "Keys: console D-pad, DOS WASD/Q, desktop WASD/arrows + Space for platformers and Esc to quit.\n"
        "Source has NOT been compiled or tested on original hardware. Do not claim a ROM exists until compilation succeeds.\n"
        "No Nintendo, Sega, Sony, Microsoft ROMs, encryption keys, firmware, copyrighted characters or proprietary SDKs included.\n"
    )
    manifest={"schema":"skeleton.ai.dragon.native_project.v1","target":target_id,
              "generation":target.generation,"style":style,"candidate_id":candidate_id,
              "status":"source_generated","toolchain":target.toolchain,
              "output_extension":target.output,"supported_mechanics":supported,
              "deferred_mechanics":deferred,"original_assets":True,
              "runtime_gameplay_mode": (
                  ("native_dda_first_person" if style in ("first_person_shooter","immersive_sim")
                   else "native_turn_based_rpg" if style=="turn_based_rpg"
                   else "native_original_sokoban" if style=="fixed_screen_puzzle"
                   else "native_timing_rhythm" if style=="rhythm_game"
                   else GENRES[style]) if target_id in ("pc_linux","pc_windows","pc_macos","steam_deck")
                  else "game_boy_scrolling_platformer" if target_id=="game_boy" and style=="side_scrolling_platformer"
                  else "original_collectible_chase"
              ),"campaign_stages": (
                  (design.stages if design is not None else 4)
                  if target_id in ("pc_linux","pc_windows","pc_macos","steam_deck")
                  else 1
              )}
    files["dragon-native-manifest.json"]=json.dumps(manifest,sort_keys=True,indent=2)+"\n"
    fingerprint=digest(files)
    return NativeProject(digest([candidate_id,target_id,style,fingerprint]),target_id,
        style,clean,"source_generated",target.toolchain,target.output,
        files,fingerprint,supported,deferred)
