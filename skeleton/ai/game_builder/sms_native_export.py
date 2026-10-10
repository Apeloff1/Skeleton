"""Actual Sega Master System Z80 32KB cartridge and authored Mode-4 VDP game.

Unlike MSX1, the Master System has no standard BIOS character ROM runtime.
This exporter creates original 8x8 4bpp planar VRAM tile art and glyphs,
initializes native Mode-4 video registers and CRAM, writes original stages
into its 32x24 tilemap, reads joypad hardware and uses the SN76489 PSG.
All mutable game state is in 8KiB SMS RAM; proprietary art/BIOS is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH = 31
MAX_HEIGHT = 21
MAX_LEVELS = 8
_TILE_NUM = {".":0,"S":0,"#":1,"C":2,"H":3,"G":4}

# Original author-owned 8x8 bitmap motifs, not characters from any game.
_ART = (
    ("........",)*8,
    ("BBBBBBBB","BooooooB","BoBBBB o".replace(" ","B"),"BoBooBoB",
     "BoBooBoB","BoBBBB o".replace(" ","B"),"BooooooB","BBBBBBBB"),
    ("........","...cc...","..cccc..",".cccccc.","..cccc..",
     "...cc...","........","........"),
    ("r......r",".r....r.","..r..r..","...rr...","...rr...",
     "..r..r..",".r....r.","r......r"),
    ("..gggg..",".gg..gg.","gg....gg","gg.gg.gg","gg.gg.gg",
     "gg....gg","gggggggg","........"),
    ("..yyyy..",".ywywyw.","ywywywyw","ywwwwwwy",
     "ywywywyw","ywwwwwwy",".yyyyyy.","..yyyy.."),
)
_FONT = (
    ("..wwww..",".ww..ww.","ww...www","ww..w.ww","ww.w..ww","www...ww",".ww..ww.","..wwww.."),
    ("...ww...", "..www...",".w.ww...","...ww...","...ww...","...ww...","..wwww..","........"),
    ("..wwww..",".ww..ww.",".....ww.","...www..","..ww....",".ww.....","wwwwwwww","........"),
    (".wwwww..","ww...ww.",".....ww.","...www..",".....ww.","ww...ww.",".wwwww..","........"),
    ("...www..","..wwww..",".ww.ww..","ww..ww..","wwwwwwww","....ww..","....ww..","........"),
    ("wwwwwww.","ww......","wwwwwww.","......ww","......ww","ww...ww.",".wwwww..","........"),
    ("..wwww..",".ww.....","ww......","wwwwwww.","ww....ww","ww....ww",".wwwwww.","........"),
    ("wwwwwwww",".....ww.","....ww..","...ww...","..ww....",".ww.....","ww......","........"),
    ("..wwww..","ww....ww","ww....ww",".wwwwww.","ww....ww","ww....ww",".wwwwww.","........"),
    (".wwwww.","ww....ww","ww....ww",".wwwwwww","......ww",".....ww.","..wwww..","........"),
)
_LABELS = (
    ("w.......","w.......","w.......","w.......","w.......","w.......","wwwwwww.","........"), # L
    ("..wwwww.",".ww.....","ww......","ww......","ww......",".ww.....","..wwwww.","........"), # C
    ("ww....ww","ww....ww","ww....ww","wwwwwwww","ww....ww","ww....ww","ww....ww","........"), # H
    (".wwwwww.","ww......","ww......",".wwwww..","......ww","......ww","wwwwww..","........"), # S
)


def _tile_bytes(rows: tuple[str, ...]) -> tuple[int, ...]:
    color = {".":0, "B":2, "o":3, "c":4, "r":5, "g":6, "y":7, "w":1}
    if len(rows) != 8 or any(len(row) != 8 or any(ch not in color for ch in row) for row in rows):
        raise ValueError("SMS Mode-4 original 8x8 tile art malformed")
    words = []
    for row in rows:
        shades = [color[ch] for ch in row]
        for plane in range(4):
            byte = sum(((shades[x] >> plane)&1) << (7-x) for x in range(8))
            words.append(byte)
    return tuple(words)


_TILES = tuple(_tile_bytes(rows) for rows in (*_ART,*_FONT,*_LABELS))
# SMS CRAM palette is a 6-bit RGB222 value, never copied commercial colors.
_CRAM = (0x00,0x3F,0x25,0x12,0x3C,0x03,0x0C,0x0F,0x15,0x2A,0x32,
         0x09,0x13,0x1B,0x2D,0x3B,0x00,0x3F,0x25,0x12,0x3C,0x03,
         0x0C,0x0F,0x15,0x2A,0x32,0x09,0x13,0x1B,0x2D,0x3B)

_ASM = r"""; Native Sega Master System 32KB nonbanked original Z80 game.
; User-created Mode-4 tiles, CRAM, joypad movement and SN76489 chimes.
org 00000h
    jp GameStart
    ds 0038h-$, 0
IRQ:
    push af
    in a, (0BFh)          ; Ack real VDP vertical interrupt status.
    pop af
    ei
    reti
    ds 0066h-$, 0
NMI:
    retn                   ; SMS pause-button NMI safely returns.

VDP_CTRL: equ 0BFh
VDP_DATA: equ 0BEh
JOY1_PORT: equ 0DCh
PSG_PORT: equ 07Fh
VRAM_NAME: equ 03800h
WIDTH: equ __WIDTH__
HEIGHT: equ __HEIGHT__
LEVELS: equ __LEVELS__
GEMS: equ __GEMS__
START_HEALTH: equ __HEALTH__
CELLS: equ WIDTH * HEIGHT
T_WALL: equ 1
T_GEM: equ 2
T_HAZARD: equ 3
T_EXIT: equ 4

; Master System has 8 KiB internal RAM at $C000-$DFFF.
Level: equ 0C000h
PlayerX: equ 0C001h
PlayerY: equ 0C002h
CandidateX: equ 0C003h
CandidateY: equ 0C004h
GemsLeft: equ 0C005h
Health: equ 0C006h
Won: equ 0C007h
Lost: equ 0C008h
Cooldown: equ 0C009h
LastTile: equ 0C00Ah
RowsRemain: equ 0C00Bh
Score: equ 0C00Ch      ; 16 bits little endian.
MapRAM: equ 0C100h

GameStart:
    di
    im 1
    ld sp, 0DFF0h
    xor a
    ld (Level), a
    ld (Won), a
    ld (Lost), a
    ld (Score), a
    ld (Score+1), a
    ld a, START_HEALTH
    ld (Health), a
    call InitVDP
    call LoadLevel
    ei
GameLoop:
    halt                    ; Real frame IRQ, not host application timer.
    ld a, 09Fh
    out (PSG_PORT), a        ; Mute one-shot PSG cue each frame.
    ld a, (Won)
    or a
    jp nz, VictoryIdle
    ld a, (Lost)
    or a
    jp nz, DefeatIdle
    ld a, (Cooldown)
    or a
    jr z, ReadPad
    dec a
    ld (Cooldown), a
    jp GameLoop

ReadPad:
    in a, (JOY1_PORT)
    bit 0, a
    jp z, MoveUp
    bit 1, a
    jp z, MoveDown
    bit 2, a
    jp z, MoveLeft
    bit 3, a
    jp z, MoveRight
    jp GameLoop
VictoryIdle:
    ; Final original game artwork remains visible. Never emit half of a
    ; VDP control command, which would corrupt the hardware address latch.
    jp GameLoop
DefeatIdle:
    jp GameLoop

MoveUp:
    ld a, (PlayerY)
    or a
    jp z, DelayMove
    dec a
    ld (CandidateY), a
    ld a, (PlayerX)
    ld (CandidateX), a
    jp CommitMove
MoveDown:
    ld a, (PlayerY)
    inc a
    ld (CandidateY), a
    ld a, (PlayerX)
    ld (CandidateX), a
    jp CommitMove
MoveLeft:
    ld a, (PlayerX)
    or a
    jp z, DelayMove
    dec a
    ld (CandidateX), a
    ld a, (PlayerY)
    ld (CandidateY), a
    jp CommitMove
MoveRight:
    ld a, (PlayerX)
    inc a
    ld (CandidateX), a
    ld a, (PlayerY)
    ld (CandidateY), a

CommitMove:
    call TryMove
DelayMove:
    ld a, 7
    ld (Cooldown), a
    jp GameLoop

TryMove:
    ld a, (CandidateX)
    cp WIDTH
    ret nc
    ld a, (CandidateY)
    cp HEIGHT
    ret nc
    ld hl, 0
    ld de, WIDTH
    ld a, (CandidateY)
    or a
    jr z, AddColumn
MultiplyRow:
    add hl, de
    dec a
    jr nz, MultiplyRow
AddColumn:
    ld a, (CandidateX)
    ld e, a
    ld d, 0
    add hl, de
    ld de, MapRAM
    add hl, de
    ld a, (hl)
    ld (LastTile), a
    cp T_WALL
    ret z
    ld a, (CandidateX)
    ld (PlayerX), a
    ld a, (CandidateY)
    ld (PlayerY), a
    ld a, (LastTile)
    cp T_GEM
    jr nz, CheckHazard
    xor a
    ld (hl), a
    ld a, (GemsLeft)
    dec a
    ld (GemsLeft), a
    ld hl, (Score)
    ld de, 10
    add hl, de
    ld (Score), hl
    ld a, 084h              ; SN76489 channel 0 tone low nibble.
    out (PSG_PORT), a
    ld a, 012h              ; Tone upper six bits: original authored note.
    out (PSG_PORT), a
    ld a, 093h              ; One-frame audible volume, then muted.
    out (PSG_PORT), a
    jp Redraw

CheckHazard:
    cp T_HAZARD
    jr nz, CheckExit
    ld a, (Health)
    dec a
    ld (Health), a
    or a
    jr nz, Redraw
    ld a, 1
    ld (Lost), a
    jp Redraw
CheckExit:
    cp T_EXIT
    jr nz, Redraw
    ld a, (GemsLeft)
    or a
    jr nz, Redraw
    ld hl, (Score)
    ld de, 100
    add hl, de
    ld (Score), hl
    ld a, (Level)
    inc a
    cp LEVELS
    jr z, WinGame
    ld (Level), a
    call LoadLevel
    ret
WinGame:
    ld a, 1
    ld (Won), a
Redraw:
    call Render
    ret

LoadLevel:
    ld a, GEMS
    ld (GemsLeft), a
    xor a
    ld (Cooldown), a
    ld a, (Level)
    ld e, a
    ld d, 0
    ld hl, StartX
    add hl, de
    ld a, (hl)
    ld (PlayerX), a
    ld hl, StartY
    add hl, de
    ld a, (hl)
    ld (PlayerY), a
    ld hl, StageMapPointers
    add hl, de
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)
    ex de, hl
    ld de, MapRAM
    ld bc, CELLS
    ldir
    call Render
    ret

; VDP: control 0xBF, data 0xBE, SN76489 PSG 0x7F.
InitVDP:
    ld hl, VDPRegisterInit
    ld b, 11
    ld c, 080h
RegLoop:
    ld a, (hl)
    out (VDP_CTRL), a
    ld a, c
    out (VDP_CTRL), a
    inc hl
    inc c
    djnz RegLoop
    ld a, 0
    out (VDP_CTRL), a
    ld a, 0C0h            ; SMS CRAM write at address 0.
    out (VDP_CTRL), a
    ld hl, OriginalCRAM
    ld b, 32
PaletteLoop:
    ld a, (hl)
    out (VDP_DATA), a
    inc hl
    djnz PaletteLoop
    ld hl, 0              ; Upload original 4bpp planar art at VRAM 0.
    call SetWriteAddress
    ld hl, OriginalTilePixels
    ld bc, TilePixelsEnd-OriginalTilePixels
ArtLoop:
    ld a, (hl)
    out (VDP_DATA), a
    inc hl
    dec bc
    ld a, b
    or c
    jr nz, ArtLoop
    ld a, 09Fh
    out (PSG_PORT), a
    ld a, 0BFh
    out (PSG_PORT), a
    ld a, 0DFh
    out (PSG_PORT), a
    ld a, 0FFh
    out (PSG_PORT), a
    ret

SetWriteAddress:
    ld a, l
    out (VDP_CTRL), a
    ld a, h
    or 040h
    out (VDP_CTRL), a
    ret

ClearName:
    ld hl, VRAM_NAME
    call SetWriteAddress
    ld bc, 1536           ; 32x24 cells, 16-bit hardware tile attribute.
ClearLoop:
    xor a
    out (VDP_DATA), a
    dec bc
    ld a, b
    or c
    jr nz, ClearLoop
    ret

; Every original maze cell is emitted as a genuinely authored SMS tile.
Render:
    call ClearName
    ld hl, MapRAM
    ld de, VRAM_NAME+64+2
    ld a, HEIGHT
    ld (RowsRemain), a
RenderRow:
    ex de, hl
    call SetWriteAddress
    ex de, hl
    ld b, WIDTH
RenderColumn:
    ld a, (hl)
    out (VDP_DATA), a
    xor a
    out (VDP_DATA), a
    inc hl
    djnz RenderColumn
    ex de, hl
    ld bc, 64
    add hl, bc
    ex de, hl
    ld a, (RowsRemain)
    dec a
    ld (RowsRemain), a
    jr nz, RenderRow
    call DrawPlayer
    call DrawHud
    ret

DrawPlayer:
    ld hl, VRAM_NAME+64+2
    ld de, 64
    ld a, (PlayerY)
    or a
    jr z, AddPlayerColumn
PlayerRows:
    add hl, de
    dec a
    jr nz, PlayerRows
AddPlayerColumn:
    ld a, (PlayerX)
    add a, a
    ld e, a
    ld d, 0
    add hl, de
    call SetWriteAddress
    ld a, 5
    out (VDP_DATA), a
    xor a
    out (VDP_DATA), a
    ret

DrawHud:
    ld hl, VRAM_NAME
    call SetWriteAddress
    ld a, 16              ; Original glyph "L".
    call EmitTile
    ld a, (Level)
    inc a
    add a, 6              ; Original 8x8 digits are tiles 6..15.
    call EmitTile
    xor a
    call EmitTile
    ld a, 17              ; "C" = crystals left.
    call EmitTile
    ld a, (GemsLeft)
    add a, 6
    call EmitTile
    xor a
    call EmitTile
    ld a, 18              ; "H" = health.
    call EmitTile
    ld a, (Health)
    add a, 6
    call EmitTile
    xor a
    call EmitTile
    ld a, 19              ; "S" = score.
    call EmitTile
    ld hl, (Score)
    ld de, 1000
    call EmitDigit
    ld de, 100
    call EmitDigit
    ld de, 10
    call EmitDigit
    ld de, 1
    call EmitDigit
    ret

EmitTile:
    out (VDP_DATA), a
    xor a
    out (VDP_DATA), a
    ret

EmitDigit:
    ld c, 0
DigitLoop:
    or a
    sbc hl, de
    jr c, DigitReady
    inc c
    jr DigitLoop
DigitReady:
    add hl, de
    ld a, c
    add a, 6
    call EmitTile
    ret

VDPRegisterInit:
    db 004h, 060h, 00Eh, 0FFh, 0FFh, 07Eh, 0FBh
    db 000h, 000h, 000h, 0FFh
OriginalCRAM:
__CRAM__
OriginalTilePixels:
__ART__
TilePixelsEnd:
StageMapPointers:
__POINTERS__
StartX: db __START_X__
StartY: db __START_Y__
__LEVEL_MAPS__
GameSignature: db "SKELSMS32"
end
"""
_MAKEFILE = """Z80ASM ?= z80asm
PYTHON ?= python3
.PHONY: all clean
all: build/skeleton-original.sms
build/skeleton-original.bin: game.asm
\tmkdir -p build
\t$(Z80ASM) -o $@ $<
build/skeleton-original.sms: build/skeleton-original.bin
\t$(PYTHON) make_sms.py --code build/skeleton-original.bin --rom $@
clean:
\trm -rf build
"""
_README = """Original 32KB Sega Master System Z80 homebrew cartridge.
Uses real Mode-4 VDP 4-plane original 8x8 art, native palette, joypad port
$DC, 50/60Hz video interrupts, PSG chimes and no commercial game assets.
Build: make with z80asm and Python 3. Final cartridge in
build/skeleton-original.sms (32KB with checksumed TMR SEGA header).
No Sega BIOS, commercial cartridge, third-party ROM or copied artwork
is bundled. Compiled ROM is not independently emulator/hardware certified.
"""


class SMSNativeError(ValueError):
    """Original Sega Master System native homebrew violates hardware or rights."""


@dataclass(frozen=True, slots=True)
class SMSSourceProject:
    asm: str
    makefile: str
    readme: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_sms_z80_mode4_32kb_cartridge_source"
    native_cartridge_compiled: bool = False
    sms_emulator_playthrough_verified: bool = False
    physical_sms_verified: bool = False


def compile_native_sms(
    world: PlayableWorld, rights: HomebrewSource, *, authorized: bool,
) -> SMSSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native SMS original authoring requires explicit authority")
    if not isinstance(world, PlayableWorld) or not isinstance(rights, HomebrewSource):
        raise SMSNativeError("typed original homebrew world and rights source required")
    if world.intent.project_id != rights.project_id:
        raise SMSNativeError("original SMS world and rights project mismatch")
    if (world.intent.width > MAX_WIDTH or world.intent.height > MAX_HEIGHT
            or len(world.levels) > MAX_LEVELS):
        raise SMSNativeError("SMS Mode4 32x24 tilemap or Z80 cartridge budget exceeded")
    if world.intent.collectibles_per_level > 9 or world.intent.starting_health > 9:
        raise SMSNativeError("SMS numeric tile HUD cannot render double-digit counters")
    reference = demonstrate_solvable(world, authorized=True)
    if reference.world_digest != world.digest or reference.final_state.status != "won":
        raise SMSNativeError("original SMS game lacks independent safe-winning replay")
    plan=compile_port(PortRequest((rights,), "sega_master_system", PortMode.REVERSE_CONSTRAINED))
    source_maps=[]
    for stage in world.levels:
        values=[_TILE_NUM[ch] for row in stage.rows for ch in row]
        if len(values)!=world.intent.width*world.intent.height:
            raise SMSNativeError("SMS original world tiles do not match target geometry")
        source_maps.append("StageMap"+str(stage.index)+": db "+", ".join(str(x) for x in values))
    replacements={
        "__WIDTH__":str(world.intent.width),
        "__HEIGHT__":str(world.intent.height),
        "__LEVELS__":str(len(world.levels)),
        "__GEMS__":str(world.intent.collectibles_per_level),
        "__HEALTH__":str(world.intent.starting_health),
        "__CRAM__":"    db "+", ".join(f"0{c:02X}h" for c in _CRAM),
        "__ART__":"\n".join(
            "    db "+", ".join(f"0{c:02X}h" for c in tile)
            for tile in _TILES
        ),
        "__POINTERS__":"\n".join("    dw StageMap"+str(i) for i in range(len(world.levels))),
        "__START_X__":", ".join(str(s.start[0]) for s in world.levels),
        "__START_Y__":", ".join(str(s.start[1]) for s in world.levels),
        "__LEVEL_MAPS__":"\n".join(source_maps),
    }
    asm=_ASM
    for marker,value in replacements.items():
        if asm.count(marker)!=1:
            raise SMSNativeError("SMS original Mode4 source template marker conflict")
        asm=asm.replace(marker,value)
    manifest=json.dumps({
        "schema":"skeleton.game_builder.native_sms_mode4_source.v1",
        "target_platform":"sega_master_system",
        "format":"sega_sms_z80_32kb_mode4_4bpp",
        "project_id":rights.project_id,
        "original_source_platform":rights.platform_id,
        "rights_evidence_sha256":rights.evidence_sha256,
        "world_digest":world.digest,
        "original_reference_digest":reference.digest,
        "port_blueprint_digest":plan.digest,
        "original_tile_count":len(_TILES),
        "original_4bpp_art_digest":sha256(bytes(n for tile in _TILES for n in tile)).hexdigest(),
        "original_rgb222_cram_digest":sha256(bytes(_CRAM)).hexdigest(),
        "screen":"32x24 Mode4 8x8 tiles",
        "joypad":"port DC active-low joypad1",
        "sound":"SN76489 at 7F",
        "native_cartridge_compiled":False,
        "sms_emulator_playthrough_verified":False,
        "original_hardware_verified":False,
        "distribution_licensed":False,
        "rights_to_commercial_IP":False,
    },sort_keys=True,indent=2)+"\n"
    digest=sha256((asm+"\0"+_MAKEFILE+"\0"+_README+"\0"+manifest).encode()).hexdigest()
    return SMSSourceProject(asm,_MAKEFILE,_README,manifest,digest)


def export_native_sms(project:SMSSourceProject,output:str|Path,*,authorized:bool)->Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("SMS homebrew source requires user authorization")
    if not isinstance(project,SMSSourceProject):
        raise SMSNativeError("typed Sega Mode4 original source required")
    root=Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True,exist_ok=False)
    from .sms_rom import get_sms_packer_script
    for name,text in (
        ("game.asm",project.asm),("Makefile",project.makefile),
        ("README.txt",project.readme),("manifest.json",project.manifest_json),
        ("make_sms.py",get_sms_packer_script()),
    ):
        with (root/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(text)
    return root
