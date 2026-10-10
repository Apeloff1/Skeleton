"""Original ColecoVision OS7/Z80/TMS9918 game cartridge authoring.

An independently authored game is translated into a true 32 KiB ColecoVision
page-$8000 Z80 cartridge. The Coleco header contains the 55AA identity,
boot vector, seven BIOS soft RST callbacks and a VBlank NMI vector, rather
than Sega's TMR SEGA layout. Original movement uses controller-1 port $FC,
selected with the $C0 joystick strobe; video uses Coleco TMS9918A $BE/$BF,
OS7 MODE_1 and LOAD_ASCII initialization, and $FF SN76489 sound.

The target has *only one KiB of real RAM* mirrored into $6000-$7FFF:
all source-derived mutable maps remain below $7300, distinct from $7300
state, $7340 controller scratch and $73FF return stack. The native binary
needs legally possessed firmware on the destination machine but does not
redistribute it or anyone else's commercial game assets.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

WIDTH_LIMIT=29
HEIGHT_LIMIT=21
LEVEL_LIMIT=8
MAP_LIMIT=0x300
_TILE={".":0,"S":0,"#":1,"C":2,"H":3,"G":4}

_ORIGINAL_8X8_TILES = [[0,0,0,16,0,0,0,0], [255,129,165,165,165,165,129,255], [24,60,126,255,255,126,60,24], [129,66,36,24,24,36,66,129], [126,66,90,90,90,90,66,126], [36,126,219,255,165,231,102,60]]
_ORIGINAL_COLOR_GROUPS = [225,81,177,129,49,161]


_ASM=r"""; Entirely new ColecoVision Z80 32KB OS7 cartridge / no copied art.
org 08000h

; 55 AA invokes immediate cartridge boot without claiming official branding.
ColecoHeader:
    dw 0AA55h
    dw 0
    dw 0
    dw 0
    dw ControllerScratch
    dw GameStart
    db 0C9h,0,0             ; $800C soft RST $08
    db 0C9h,0,0             ; $800F soft RST $10
    db 0C9h,0,0             ; $8012 soft RST $18
    db 0C9h,0,0             ; $8015 soft RST $20
    db 0C9h,0,0             ; $8018 soft RST $28
    db 0C9h,0,0             ; $801B soft RST $30
    db 0C9h,0,0             ; $801E soft RST $38
    jp VBlankNMI            ; $8021 BIOS redirects NMI here.
    db "ORIGINAL STAR QUEST/INDEPENDENT GAME/2026"
    db 0

CV_MODE1: equ 01F85h
CV_ASCII: equ 01F7Fh
VDP_CTRL: equ 0BFh
VDP_DATA: equ 0BEh
JOY_SELECT: equ 0C0h
JOY1: equ 0FCh
PSG: equ 0FFh
BG_NAME: equ 01800h
WIDTH: equ __WIDTH__
HEIGHT: equ __HEIGHT__
LEVELS: equ __LEVELS__
GEMS: equ __GEMS__
HEALTH_START: equ __HEALTH__
CELLS: equ WIDTH*HEIGHT
T_WALL: equ 1
T_GEM: equ 2
T_DANGER: equ 3
T_GOAL: equ 4

; Physical machine RAM is $6000-$63FF, echoed at $7000-$73FF.
; DO NOT use $C000: that is ColecoVision game cartridge ROM.
MapRAM: equ 07000h
Stage: equ 07300h
HeroX: equ 07301h
HeroY: equ 07302h
TryX: equ 07303h
TryY: equ 07304h
GemsLeft: equ 07305h
Life: equ 07306h
Won: equ 07307h
Dead: equ 07308h
Cooldown: equ 07309h
LastTile: equ 0730Ah
RenderRows: equ 0730Bh
RenderCols: equ 0730Ch
Points: equ 0730Dh
ControllerScratch: equ 07340h

VBlankNMI:
    push af
    in a,(VDP_CTRL)          ; Acknowledge physical TMS9918A vertical NMI.
    pop af
    retn

GameStart:
    di
    ld sp,073F0h
    xor a
    ld (Stage),a
    ld (Won),a
    ld (Dead),a
    ld (Points),a
    ld (Points+1),a
    ld a,HEALTH_START
    ld (Life),a
    call CV_MODE1
    call CV_ASCII           ; BIOS renders ASCII patterns in VDP VRAM.
    call InitOriginalArt    ; Original 8x8 graphics, colors and dragon hero.
    ld a,0E0h              ; VDP register 1: 16K/display/VBlank enabled.
    out (VDP_CTRL),a
    ld a,081h
    out (VDP_CTRL),a
    xor a
    out (JOY_SELECT),a     ; Hardware switches to joystick directions.
    call LoadStage
GameLoop:
    halt                   ; TMS9918A NMI releases HALT each video frame.
    ld a,09Fh
    out (PSG),a            ; Stop last frame's original sound.
    ld a,(Won)
    or a
    jr nz,Terminal
    ld a,(Dead)
    or a
    jr nz,Terminal
    ld a,(Cooldown)
    or a
    jr z,Poll
    dec a
    ld (Cooldown),a
    jr GameLoop
Poll:
    in a,(JOY1)            ; P1, joystick mode, active-low UDLR.
    bit 0,a
    jp z,MoveUp
    bit 1,a
    jp z,MoveRight
    bit 2,a
    jp z,MoveDown
    bit 3,a
    jp z,MoveLeft
    jp GameLoop
Terminal:
    jp GameLoop

MoveUp:
    ld a,(HeroY)
    or a
    jp z,DelayMove
    dec a
    ld (TryY),a
    ld a,(HeroX)
    ld (TryX),a
    jp Advance
MoveDown:
    ld a,(HeroY)
    inc a
    ld (TryY),a
    ld a,(HeroX)
    ld (TryX),a
    jp Advance
MoveLeft:
    ld a,(HeroX)
    or a
    jp z,DelayMove
    dec a
    ld (TryX),a
    ld a,(HeroY)
    ld (TryY),a
    jp Advance
MoveRight:
    ld a,(HeroX)
    inc a
    ld (TryX),a
    ld a,(HeroY)
    ld (TryY),a

Advance:
    call TryAdvance
DelayMove:
    ld a,7
    ld (Cooldown),a
    jp GameLoop

TryAdvance:
    ld a,(TryX)
    cp WIDTH
    ret nc
    ld a,(TryY)
    cp HEIGHT
    ret nc
    ld hl,0
    ld de,WIDTH
    ld a,(TryY)
    or a
    jr z,AddX
MulY:
    add hl,de
    dec a
    jr nz,MulY
AddX:
    ld a,(TryX)
    ld e,a
    ld d,0
    add hl,de
    ld de,MapRAM
    add hl,de
    ld a,(hl)
    ld (LastTile),a
    cp T_WALL
    ret z
    ld a,(TryX)
    ld (HeroX),a
    ld a,(TryY)
    ld (HeroY),a
    ld a,(LastTile)
    cp T_GEM
    jr nz,Hazard
    xor a
    ld (hl),a
    ld a,(GemsLeft)
    dec a
    ld (GemsLeft),a
    ld hl,(Points)
    ld de,10
    add hl,de
    ld (Points),hl
    ld a,084h
    out (PSG),a
    ld a,012h
    out (PSG),a
    ld a,093h
    out (PSG),a
    jp Redraw
Hazard:
    cp T_DANGER
    jr nz,Goal
    ld a,(Life)
    dec a
    ld (Life),a
    or a
    jr nz,Redraw
    ld a,1
    ld (Dead),a
    jp Redraw
Goal:
    cp T_GOAL
    jr nz,Redraw
    ld a,(GemsLeft)
    or a
    jr nz,Redraw
    ld hl,(Points)
    ld de,100
    add hl,de
    ld (Points),hl
    ld a,(Stage)
    inc a
    cp LEVELS
    jr z,Victory
    ld (Stage),a
    call LoadStage
    ret
Victory:
    ld a,1
    ld (Won),a
Redraw:
    call DrawWorld
    ret

LoadStage:
    ld a,GEMS
    ld (GemsLeft),a
    xor a
    ld (Cooldown),a
    ld a,(Stage)
    ld e,a
    ld d,0
    ld hl,StartX
    add hl,de
    ld a,(hl)
    ld (HeroX),a
    ld hl,StartY
    add hl,de
    ld a,(hl)
    ld (HeroY),a
    ld hl,LevelPointers
    add hl,de
    add hl,de
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld de,MapRAM
    ld bc,CELLS
    ldir
    call DrawWorld
    ret

InitOriginalArt:
    ; Mode-0 (Graphics I): one color entry per eight 8x8 characters.
    ; Our original gameplay tiles use separate color groups: $80/$88/...
    ld hl,00400h            ; tile #128 pattern data in VRAM.
    ld de,OriginalArtBytes
    ld b,6
UploadTile:
    push bc
    push hl
    call SetVRAM
    pop hl
    ld c,8
UploadEightRows:
    ld a,(de)
    out (VDP_DATA),a
    inc de
    dec c
    jr nz,UploadEightRows
    ld bc,00040h           ; Next group of 8 glyphs = 8*8 bytes.
    add hl,bc
    pop bc
    djnz UploadTile
    ld hl,02010h           ; color group 16, pattern #128.
    call SetVRAM
    ld hl,OriginalGroupColors
    ld b,6
UploadColors:
    ld a,(hl)
    out (VDP_DATA),a
    inc hl
    djnz UploadColors
    ret

SetVRAM:
    ld a,l
    out (VDP_CTRL),a
    ld a,h
    or 040h
    out (VDP_CTRL),a
    ret

; TMS9918A color mode 1: ASCII patterns and $1800 name table.
DrawWorld:
    ; Coleco's VDP asserts NMI, not a maskable IRQ. DI does NOT guard
    ; the two-byte $BF address latch. Quiesce VBlank at the VDP itself
    ; while changing tile/name-table addresses, then restore at exit.
    in a,(VDP_CTRL)           ; Clear any pending VBlank and reset latch.
    ld a,0C0h               ; R1: display ON; VDP interrupts OFF.
    out (VDP_CTRL),a
    ld a,081h
    out (VDP_CTRL),a
    ld hl,BG_NAME
    call SetVRAM
    ld bc,768
    ld a,' '
ClearVDP:
    out (VDP_DATA),a
    dec bc
    ld d,a
    ld a,b
    or c
    ld a,d
    jr nz,ClearVDP

    ld hl,MapRAM
    ld de,BG_NAME+33
    ld a,HEIGHT
    ld (RenderRows),a
DrawRow:
    ex de,hl
    call SetVRAM
    ex de,hl
    ld b,WIDTH
DrawColumn:
    ld a,(hl)
    push hl
    push de                  ; Preserve VRAM next-row pointer across glyph lookup.
    ld e,a
    ld d,0
    ld hl,TileChars
    add hl,de
    ld a,(hl)
    out (VDP_DATA),a
    pop de
    pop hl
    inc hl
    djnz DrawColumn
    ex de,hl
    ld bc,32
    add hl,bc
    ex de,hl
    ld a,(RenderRows)
    dec a
    ld (RenderRows),a
    jr nz,DrawRow
    ld hl,BG_NAME
    call SetVRAM
    ld hl,TitleChars
    call PrintString
    ld hl,BG_NAME+704
    call SetVRAM
    ld hl,HudChars
    call PrintString
    ld a,(Stage)
    inc a
    add a,'0'
    out (VDP_DATA),a
    ld hl,CrystalChars
    call PrintString
    ld a,(GemsLeft)
    add a,'0'
    out (VDP_DATA),a
    ld hl,HPChars
    call PrintString
    ld a,(Life)
    add a,'0'
    out (VDP_DATA),a
    ld hl,BG_NAME+736
    call SetVRAM
    ld hl,ScoreChars
    call PrintString
    ld hl,(Points)
    ld de,1000
    call PrintDigit
    ld de,100
    call PrintDigit
    ld de,10
    call PrintDigit
    ld de,1
    call PrintDigit
    ld hl,BG_NAME+33
    ld de,32
    ld a,(HeroY)
    or a
    jr z,AddHeroX
HeroRows:
    add hl,de
    dec a
    jr nz,HeroRows
AddHeroX:
    ld a,(HeroX)
    ld e,a
    ld d,0
    add hl,de
    call SetVRAM
    ld a,0A8h              ; Unique original baby dragon at tile #168.
    out (VDP_DATA),a
    in a,(VDP_CTRL)          ; Do not re-assert stale VBlank immediately.
    ld a,0E0h              ; R1: display ON and fresh NMI each frame.
    out (VDP_CTRL),a
    ld a,081h
    out (VDP_CTRL),a
    ret

PrintString:
    ld a,(hl)
    or a
    ret z
    inc hl
    out (VDP_DATA),a
    jr PrintString

PrintDigit:
    ld c,0
DivLoop:
    or a
    sbc hl,de
    jr c,DigitDone
    inc c
    jr DivLoop
DigitDone:
    add hl,de
    ld a,c
    add a,'0'
    out (VDP_DATA),a
    ret

TitleChars: db "INDEPENDENT COLECO STAR MAZE",0
HudChars: db "LEVEL:",0
CrystalChars: db " GEMS:",0
HPChars: db " HP:",0
ScoreChars: db "SCORE:",0
TileChars: db 080h,088h,090h,098h,0A0h
OriginalArtBytes:
__ORIGINAL_ART__
OriginalGroupColors:
__ORIGINAL_COLORS__
LevelPointers:
__POINTERS__
StartX: db __START_X__
StartY: db __START_Y__
__MAPS__
GameSignature: db "SKELCOL32"
end
"""
_MAKEFILE="""Z80ASM ?= z80asm
PYTHON ?= python3
.PHONY: all clean
all: build/original-coleco.col
build/original-coleco.bin: game.asm
\tmkdir -p build
\t$(Z80ASM) -o $@ $<
build/original-coleco.col: build/original-coleco.bin
\t$(PYTHON) make_col.py --code build/original-coleco.bin --rom $@
clean:
\trm -rf build
"""

class ColecoNativeError(ValueError):
    """Invalid original ColecoVision gameplay, one-KiB RAM budget or rights."""

@dataclass(frozen=True,slots=True)
class ColecoSourceProject:
    asm:str
    makefile:str
    manifest_json:str
    content_digest:str
    artifact_kind:str="native_colecovision_32kb_z80_tms9918_source"
    binary_compiled:bool=False
    cpu_playthrough_verified:bool=False
    physical_hardware_verified:bool=False

def compile_native_coleco(world:PlayableWorld,rights:HomebrewSource,*,authorized:bool)->ColecoSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native original ColecoVision cartridge requires authorization")
    if not isinstance(world,PlayableWorld) or not isinstance(rights,HomebrewSource):
        raise ColecoNativeError("typed original game and rights source required")
    if world.intent.project_id!=rights.project_id:
        raise ColecoNativeError("ColecoVision world and original-homebrew rights mismatch")
    if (world.intent.width>WIDTH_LIMIT or world.intent.height>HEIGHT_LIMIT
        or len(world.levels)>LEVEL_LIMIT or world.intent.width*world.intent.height>MAP_LIMIT):
        raise ColecoNativeError("ColecoVision 32x24 VRAM and mirrored one-KiB RAM budget exceeded")
    if world.intent.collectibles_per_level>9 or world.intent.starting_health>9:
        raise ColecoNativeError("ColecoVision BIOS text HUD counter exceeded")
    proof=demonstrate_solvable(world,authorized=True)
    if proof.world_digest!=world.digest or proof.final_state.status!="won":
        raise ColecoNativeError("ColecoVision stage lacks independent safe-winning replay")
    port=compile_port(PortRequest((rights,), "colecovision", PortMode.REVERSE_CONSTRAINED))
    maps=[]
    for stage in world.levels:
        pixels=[_TILE[ch] for row in stage.rows for ch in row]
        if len(pixels)!=world.intent.width*world.intent.height:
            raise ColecoNativeError("author-generated Coleco level geometry invalid")
        maps.append("StageMap"+str(stage.index)+": db "+", ".join(map(str,pixels)))
    replacements={
        "__WIDTH__":str(world.intent.width),
        "__HEIGHT__":str(world.intent.height),
        "__LEVELS__":str(len(world.levels)),
        "__GEMS__":str(world.intent.collectibles_per_level),
        "__HEALTH__":str(world.intent.starting_health),
        "__POINTERS__":"\n".join("    dw StageMap"+str(i) for i in range(len(world.levels))),
        "__START_X__":", ".join(str(l.start[0]) for l in world.levels),
        "__START_Y__":", ".join(str(l.start[1]) for l in world.levels),
        "__MAPS__":"\n".join(maps),
        "__ORIGINAL_ART__":"\n".join(
            "    db "+", ".join(f"0{byte:02X}h" for byte in tile)
            for tile in _ORIGINAL_8X8_TILES
        ),
        "__ORIGINAL_COLORS__":"    db "+", ".join(f"0{color:02X}h" for color in _ORIGINAL_COLOR_GROUPS),
    }
    program=_ASM
    for key,value in replacements.items():
        if program.count(key)!=1:
            raise ColecoNativeError("Coleco original source code marker collision")
        program=program.replace(key,value)
    manifest=json.dumps({
        "schema":"skeleton.game_builder.native_colecovision_source.v1",
        "platform":"colecovision",
        "native_hardware":"ColecoVision Z80 OS7 BIOS TMS9918A SN76489",
        "rom_base":"0x8000",
        "cartridge_magic":"55AA direct boot",
        "ram_physical_kib":1,
        "ram_mirror":"0x7000-0x73ff mirrored",
        "map_ram_base":"0x7000",
        "game_state_ram_base":"0x7300",
        "video_port":0xBE,
        "video_control_port":0xBF,
        "joypad_mode_select_port":0xC0,
        "joypad_1_port":0xFC,
        "psg_port":0xFF,
        "gameplay_levels":len(world.levels),
        "world_digest":world.digest,
        "reference_replay_digest":proof.digest,
        "source_project_id":rights.project_id,
        "source_historical_platform":rights.platform_id,
        "author_evidence_sha256":rights.evidence_sha256,
        "port_plan_digest":port.digest,
        "original_source_only":True,
        "native_binary_compiled":False,
        "emulator_full_playthrough_verified":False,
        "physical_hardware_verified":False,
        "redistribution_licensed":False,
        "original_8x8_tile_count":len(_ORIGINAL_8X8_TILES),
        "original_tile_sha256":sha256(bytes(v for tile in _ORIGINAL_8X8_TILES for v in tile)).hexdigest(),
        "original_palette_sha256":sha256(bytes(_ORIGINAL_COLOR_GROUPS)).hexdigest(),
        "color_table_base":"0x2000",
        "graphics_pattern_base":"0x0000",
        "distinct_background_color_groups":len(_ORIGINAL_COLOR_GROUPS),
        "player_art":"original_companion_dragon_8x8",
        "third_party_firmware_included":False,
    },sort_keys=True,indent=2)+"\n"
    digest=sha256((program+"\0"+_MAKEFILE+"\0"+manifest).encode()).hexdigest()
    return ColecoSourceProject(program,_MAKEFILE,manifest,digest)

def export_native_coleco(project:ColecoSourceProject,destination:str|Path,*,authorized:bool)->Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("original ColecoVision source export requires explicit authority")
    if not isinstance(project,ColecoSourceProject):
        raise ColecoNativeError("typed original ColecoVision project required")
    expected=sha256((project.asm+"\0"+project.makefile+"\0"+project.manifest_json).encode()).hexdigest()
    if expected!=project.content_digest:
        raise ColecoNativeError("original Coleco machine-source project content changed")
    folder=Path(destination)
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(str(folder))
    folder.mkdir(parents=True,exist_ok=False)
    from .coleco_rom import get_col_packer_script
    for name,body in (
        ("game.asm",project.asm),("Makefile",project.makefile),
        ("manifest.json",project.manifest_json),
        ("make_col.py",get_col_packer_script()),
    ):
        with (folder/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(body)
    return folder
