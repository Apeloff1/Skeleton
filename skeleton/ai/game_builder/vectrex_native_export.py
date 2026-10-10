"""Independent vector-screen 6809 game for authentic original Vectrex cartridges.

The Vectrex has NO raster display, tile screen, pixel framebuffer or video
palette. This backend translates an independently solvable original game
into genuine MC6809 ROM code with Wait_Recal beam synchronization, real
digital joystick sampling and vector-drawn player dragon and immediate
3x3 surroundings. Only original art and level data are emitted.

Hardware limits are fail-closed: cartridge at 0x0000-0x7FFF, BIOS ROM at
0xF000+, shared ~1KiB RAM at 0xC800-0xCBFF, source game maps at 0xC900,
mutable state at 0xCB00, vector stack at 0xCBF0, and BIOS runtime state
at 0xC800-0xC8FF. Firmware bytes are never bundled.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH=17
MAX_HEIGHT=15
MAX_LEVELS=8
MAX_MAP_BYTES=255
_TILES={".":0,"S":0,"#":1,"C":2,"H":3,"G":4}

_ASM=r"""; Original authentic Vectrex 6809 vector adventure: NO video pixels.
        ORG     $0000
CartridgeHeader:
        FCB     $67,$20
        FCC     "GCE 2026"
        FCB     $80
        FDB     SilentMusic
        FDB     $F850
        FDB     $30B8
        FCC     "ORIGINAL DRAGON STARS"
        FCB     $80,$00

Wait_Recal      EQU     $F192
Joy_Digital     EQU     $F1F8
Intensity_a     EQU     $F2AB
Moveto_d_7F     EQU     $F2FC
Draw_Line_d     EQU     $F3DF
Reset0Ref       EQU     $F354
DP_to_D0        EQU     $F1AA
Vec_Joy_1_X     EQU     $C81B
Vec_Joy_1_Y     EQU     $C81C
Vec_Joy_Mux_1_X EQU     $C81F
Vec_Joy_Mux_1_Y EQU     $C820

WIDTH           EQU     __WIDTH__
HEIGHT          EQU     __HEIGHT__
LEVELS          EQU     __LEVELS__
GEMS            EQU     __GEMS__
HEALTH_START    EQU     __HEALTH__
CELLS           EQU     WIDTH*HEIGHT
T_WALL          EQU     1
T_GEM           EQU     2
T_HAZARD        EQU     3
T_EXIT          EQU     4

MapRAM          EQU     $C900
Level           EQU     $CB00
HeroX           EQU     $CB01
HeroY           EQU     $CB02
TryX            EQU     $CB03
TryY            EQU     $CB04
GemsLeft        EQU     $CB05
Health          EQU     $CB06
Won             EQU     $CB07
Lost            EQU     $CB08
Cooldown        EQU     $CB09
LastTile        EQU     $CB0A
Points          EQU     $CB0B
DrawOffX        EQU     $CB0D
DrawOffY        EQU     $CB0E
RenderTile      EQU     $CB0F

GameStart:
        LDS     #$CBF0
        CLRA
        STA     Level
        STA     Won
        STA     Lost
        STD     Points
        LDA     #HEALTH_START
        STA     Health
        LDA     #$01
        STA     Vec_Joy_Mux_1_X
        LDA     #$03
        STA     Vec_Joy_Mux_1_Y
        JSR     LoadLevel

GameLoop:
        JSR     Wait_Recal       ; Beam recalibration every frame, REQUIRED.
        JSR     DP_to_D0         ; Vectrex BIOS routines require DP=$D0.
        LDA     #$5F
        JSR     Intensity_a
        JSR     RenderView
        LDA     Won
        BNE     GameLoop
        LDA     Lost
        BNE     GameLoop
        LDA     Cooldown
        BEQ     ReadJoy
        DECA
        STA     Cooldown
        BRA     GameLoop
ReadJoy:
        JSR     DP_to_D0
        JSR     Joy_Digital      ; Actual analog-stick hardware read, digital.
        LDA     Vec_Joy_1_X
        BGT     MoveRight
        BLT     MoveLeft
        LDA     Vec_Joy_1_Y
        BGT     MoveUp
        BLT     MoveDown
        BRA     GameLoop

MoveUp:
        LDA     HeroY
        BEQ     DelayMove
        DECA
        STA     TryY
        LDA     HeroX
        STA     TryX
        BRA     CommitMove
MoveDown:
        LDA     HeroY
        INCA
        STA     TryY
        LDA     HeroX
        STA     TryX
        BRA     CommitMove
MoveLeft:
        LDA     HeroX
        BEQ     DelayMove
        DECA
        STA     TryX
        LDA     HeroY
        STA     TryY
        BRA     CommitMove
MoveRight:
        LDA     HeroX
        INCA
        STA     TryX
        LDA     HeroY
        STA     TryY

CommitMove:
        JSR     TryAdvance
DelayMove:
        LDA     #$07
        STA     Cooldown
        JMP     GameLoop

; True source-authored collision and score logic in physical Vectrex RAM.
TryAdvance:
        LDA     TryX
        CMPA    #WIDTH
        BHS     RefuseMove
        LDA     TryY
        CMPA    #HEIGHT
        BHS     RefuseMove
        JSR     LocateCell
        LDA     ,X
        STA     LastTile
        CMPA    #T_WALL
        BEQ     RefuseMove
        LDA     TryX
        STA     HeroX
        LDA     TryY
        STA     HeroY
        LDA     LastTile
        CMPA    #T_GEM
        BNE     CheckHazard
        CLR     ,X
        DEC     GemsLeft
        LDD     Points
        ADDD    #10
        STD     Points
        BRA     DoneMove
CheckHazard:
        CMPA    #T_HAZARD
        BNE     CheckExit
        DEC     Health
        BNE     DoneMove
        LDA     #1
        STA     Lost
        BRA     DoneMove
CheckExit:
        CMPA    #T_EXIT
        BNE     DoneMove
        TST     GemsLeft
        BNE     DoneMove
        LDD     Points
        ADDD    #100
        STD     Points
        LDA     Level
        INCA
        CMPA    #LEVELS
        BEQ     WinGame
        STA     Level
        JSR     LoadLevel
        BRA     DoneMove
WinGame:
        LDA     #1
        STA     Won
DoneMove:
RefuseMove:
        RTS

; X = real MapRAM + 8-bit row * WIDTH + column.
LocateCell:
        LDA     TryY
        LDB     #WIDTH
        MUL
        ADDB    TryX
        ADCA    #0
        LDX     #MapRAM
        LEAX    D,X
        RTS

LoadLevel:
        LDA     #GEMS
        STA     GemsLeft
        CLRA
        STA     Cooldown
        LDB     Level
        LSLB
        LDX     #StagePointers
        LDX     B,X
        LDU     #MapRAM
        LDY     #CELLS
CopyMap:
        LDA     ,X+
        STA     ,U+
        LEAY    -1,Y
        BNE     CopyMap
        LDB     Level
        LDX     #StartX
        LDA     B,X
        STA     HeroX
        LDX     #StartY
        LDA     B,X
        STA     HeroY
        RTS

; A real 6809 vector CRT cannot display every 17x15 tile every 50Hz:
; render a 3x3 cross of four neighbors and a tiny flying dragon.
RenderView:
        JSR     DrawHero
        LDA     HeroX
        BEQ     ViewRight
        DECA
        STA     TryX
        LDA     HeroY
        STA     TryY
        LDA     #$D8            ; left relative x = -40.
        STA     DrawOffX
        CLRA
        STA     DrawOffY
        JSR     DrawNeighbor
ViewRight:
        LDA     HeroX
        INCA
        CMPA    #WIDTH
        BHS     ViewUp
        STA     TryX
        LDA     HeroY
        STA     TryY
        LDA     #40
        STA     DrawOffX
        CLRA
        STA     DrawOffY
        JSR     DrawNeighbor
ViewUp:
        LDA     HeroY
        BEQ     ViewDown
        DECA
        STA     TryY
        LDA     HeroX
        STA     TryX
        CLRA
        STA     DrawOffX
        LDA     #40
        STA     DrawOffY
        JSR     DrawNeighbor
ViewDown:
        LDA     HeroY
        INCA
        CMPA    #HEIGHT
        BHS     RenderComplete
        STA     TryY
        LDA     HeroX
        STA     TryX
        CLRA
        STA     DrawOffX
        LDA     #$D8            ; down is signed -40 on vector CRT.
        STA     DrawOffY
        JSR     DrawNeighbor
RenderComplete:
        RTS

; A small bright vector dragon with ears, wings, tail and facial triangle.
DrawHero:
        JSR     Reset0Ref
        LDD     #$F808
        JSR     Moveto_d_7F
        LDD     #$1000
        JSR     Draw_Line_d
        LDD     #$F810
        JSR     Draw_Line_d
        LDD     #$F8F0
        JSR     Draw_Line_d
        LDD     #$1000
        JSR     Draw_Line_d
        LDD     #$F008
        JSR     Draw_Line_d
        RTS

DrawNeighbor:
        JSR     LocateCell
        LDA     ,X
        STA     RenderTile
        BEQ     NoVector
        JSR     Reset0Ref
        LDA     DrawOffY
        LDB     DrawOffX
        JSR     Moveto_d_7F
        LDA     RenderTile
        CMPA    #T_WALL
        BEQ     DrawWall
        CMPA    #T_GEM
        BEQ     DrawCrystal
        CMPA    #T_HAZARD
        BEQ     DrawDanger
        ; Exit portal shown with a distinct three-sided vector motif.
        LDD     #$0808
        JSR     Draw_Line_d
        LDD     #$F008
        JSR     Draw_Line_d
        LDD     #$0808
        JSR     Draw_Line_d
        RTS
DrawWall:
        LDD     #$1000
        JSR     Draw_Line_d
        LDD     #$0010
        JSR     Draw_Line_d
        LDD     #$F000
        JSR     Draw_Line_d
        LDD     #$00F0
        JSR     Draw_Line_d
        RTS
DrawCrystal:
        LDD     #$0808
        JSR     Draw_Line_d
        LDD     #$F808
        JSR     Draw_Line_d
        LDD     #$F8F8
        JSR     Draw_Line_d
        LDD     #$08F8
        JSR     Draw_Line_d
        RTS
DrawDanger:
        LDD     #$1010
        JSR     Draw_Line_d
        RTS
NoVector:
        RTS

StagePointers:
__POINTERS__
StartX:
        FCB     __START_X__
StartY:
        FCB     __START_Y__
__MAPS__
GameSignature:
        FCC     "SKELVEC6809"
SilentMusic:
        FDB     $FEE8,$FEB6
        FCB     0,$80,0,$80
        END
"""
_MAKEFILE="""LWASM ?= lwasm
.PHONY: all clean
all: build/original-vectrex.bin
build/original-vectrex.bin: game.asm
\tmkdir -p build
\t$(LWASM) --format=raw --output=$@ $<
clean:
\trm -rf build
"""


class VectrexNativeError(ValueError):
    """Original vector CRT/physical shared-RAM source exceeds Vectrex budget."""


@dataclass(frozen=True,slots=True)
class VectrexSourceProject:
    asm:str
    makefile:str
    manifest_json:str
    content_digest:str
    artifact_kind:str="native_vectrex_mc6809_vector_cartridge_source"
    compiled_rom:bool=False
    vector_display_verified:bool=False
    physical_hardware_verified:bool=False


def compile_native_vectrex(world:PlayableWorld,rights:HomebrewSource,*,authorized:bool)->VectrexSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Vectrex native original cartridge requires explicit authorization")
    if not isinstance(world,PlayableWorld) or not isinstance(rights,HomebrewSource):
        raise VectrexNativeError("Vectrex requires typed original game and author evidence")
    if world.intent.project_id!=rights.project_id:
        raise VectrexNativeError("Vectrex authored game and rights project mismatch")
    if (world.intent.width>MAX_WIDTH or world.intent.height>MAX_HEIGHT
        or world.intent.width*world.intent.height>MAX_MAP_BYTES or len(world.levels)>MAX_LEVELS):
        raise VectrexNativeError("Vectrex 1KiB RAM or vector 3x3 view budget exceeded")
    if world.intent.collectibles_per_level>9 or world.intent.starting_health>9:
        raise VectrexNativeError("Vectrex native game state budget exceeded")
    proof=demonstrate_solvable(world,authorized=True)
    if proof.world_digest!=world.digest or proof.final_state.status!="won":
        raise VectrexNativeError("Vectrex game has no authentic winnable gameplay reference")
    port=compile_port(PortRequest((rights,),"vectrex",PortMode.REVERSE_CONSTRAINED))
    original=[]
    for stage in world.levels:
        tiles=[_TILES[ch] for line in stage.rows for ch in line]
        if len(tiles)!=world.intent.width*world.intent.height:
            raise VectrexNativeError("Vectrex original source world geometry corrupted")
        original.append("StageMap"+str(stage.index)+":\n        FCB "+",".join(str(v) for v in tiles))
    repl={
        "__WIDTH__":str(world.intent.width),"__HEIGHT__":str(world.intent.height),
        "__LEVELS__":str(len(world.levels)),"__GEMS__":str(world.intent.collectibles_per_level),
        "__HEALTH__":str(world.intent.starting_health),
        "__POINTERS__":"\n".join("        FDB StageMap"+str(i) for i in range(len(world.levels))),
        "__START_X__":",".join(str(s.start[0]) for s in world.levels),
        "__START_Y__":",".join(str(s.start[1]) for s in world.levels),
        "__MAPS__":"\n".join(original),
    }
    src=_ASM
    for key,val in repl.items():
        if src.count(key)!=1:
            raise VectrexNativeError("Vectrex original MC6809 compiler token collision")
        src=src.replace(key,val)
    manifest=json.dumps({
        "schema":"skeleton.game_builder.native_vectrex_mc6809.v1",
        "target_platform":"vectrex",
        "native_cpu":"Motorola 6809",
        "display":"electrostatic_vector_CRT_no_raster_pixels",
        "view":"three_by_three_local_cross_original_vector_geometry",
        "rom_base":0,"rom_capacity_bytes":32768,
        "physical_shared_ram_kib":1,
        "gameplay_map_ram":"C900",
        "game_state_ram":"CB00",
        "game_stack":"CBF0",
        "world_digest":world.digest,
        "winning_reference_digest":proof.digest,
        "project_id":rights.project_id,
        "source_hardware":rights.platform_id,
        "rights_evidence_sha256":rights.evidence_sha256,
        "blueprint_digest":port.digest,
        "levels":len(world.levels),
        "width":world.intent.width,"height":world.intent.height,
        "original_dragon_vector_shape":True,
        "compiled_rom":False,
        "emulator_gameplay_verified":False,
        "physical_console_verified":False,
        "commercial_game_license_verified":False,
        "proprietary_vectrex_bios_included":False,
    },sort_keys=True,indent=2)+"\n"
    return VectrexSourceProject(src,_MAKEFILE,manifest,sha256((src+"\0"+_MAKEFILE+"\0"+manifest).encode()).hexdigest())


def export_native_vectrex(project:VectrexSourceProject,destination:str|Path,*,authorized:bool)->Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Vectrex original source export requires author permission")
    if not isinstance(project,VectrexSourceProject):
        raise VectrexNativeError("typed original Vectrex source required")
    if sha256((project.asm+"\0"+project.makefile+"\0"+project.manifest_json).encode()).hexdigest()!=project.content_digest:
        raise VectrexNativeError("original Vectrex source custody digest modified")
    target=Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError(str(target))
    target.mkdir(parents=True,exist_ok=False)
    for name,body in (("game.asm",project.asm),("Makefile",project.makefile),
                      ("manifest.json",project.manifest_json)):
        with (target/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(body)
    return target
