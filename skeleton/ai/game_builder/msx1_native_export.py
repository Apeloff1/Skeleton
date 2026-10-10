"""Genuine original MSX1 16KB Z80 ROM cartridge exporter.

Targets MSX1 BIOS, 40x24 SCREEN 0, character VDP, BIOS joystick 1,
keyboard, sound and RAM-page-3 game state. These are native cartridge ROM
sources; nothing is a renamed DOS/ZX binary or a web application. Output does
not contain third-party MSX firmware, licensed artwork or commercial ROMs.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH = 37
MAX_HEIGHT = 21
MAX_LEVELS = 8
_TILE_NUM = {".":0, "S":0, "#":1, "C":2, "H":3, "G":4}

_ASM = r"""; Original MSX1 16KB 0x4000-0x7FFF cartridge.
; Author-produced 6502-free Z80 executable. NO commercial game data.
org 04000h

MSX_INITXT: equ 0006Ch
MSX_CHGCLR: equ 00062h
MSX_CHPUT: equ 000A2h
MSX_CHSNS: equ 0009Ch
MSX_CHGET: equ 0009Fh
MSX_BEEP: equ 000C0h
MSX_CLS: equ 000C3h
MSX_POSIT: equ 000C6h
MSX_GTSTCK: equ 000D5h
MSX_FORCLR: equ 0F3E9h
MSX_BAKCLR: equ 0F3EAh
MSX_BDRCLR: equ 0F3EBh

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

; All mutable gameplay lives in explicitly reserved page-3 RAM, never ROM.
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
RowCount: equ 0C00Bh
ColCount: equ 0C00Ch
Score: equ 0C00Dh     ; Little-endian 16-bit.
MapRAM: equ 0C100h    ; CELLS bytes, <= 777; avoids MSX BIOS system vars.

ROMHeader:
    db "AB"
    dw GameStart          ; Cartridge INIT entry in page 1.
    dw 0                  ; Statement hook (unused).
    dw 0                  ; Device hook (unused).
    dw 0                  ; BASIC program hook (unused).
    dw 0
    dw 0
    dw 0                  ; Reserved header bytes.

GameStart:
    xor a
    ld (Level), a
    ld (Won), a
    ld (Lost), a
    ld (Score), a
    ld (Score+1), a
    ld a, START_HEALTH
    ld (Health), a
    ld a, 15
    ld (MSX_FORCLR), a
    ld a, 1
    ld (MSX_BAKCLR), a
    ld (MSX_BDRCLR), a
    call MSX_INITXT       ; Real BIOS 40-column text VDP mode 0.
    call MSX_CHGCLR
    call LoadLevel
MainLoop:
    halt                  ; Hardware VBlank interrupt, bounded keyboard poll.
    ld a, (Won)
    or a
    jp nz, FinalGame
    ld a, (Lost)
    or a
    jp nz, FinalGame
    ld a, (Cooldown)
    or a
    jr z, ReadKeyboard
    dec a
    ld (Cooldown), a
    jp MainLoop

ReadKeyboard:
    call MSX_CHSNS
    jr z, ReadJoystick    ; No queued key; joystick remains responsive.
    call MSX_CHGET
    cp 27
    ret z                 ; Escape safely returns from ROM INIT call.
    cp 'W'
    jp z, MoveUp
    cp 'w'
    jp z, MoveUp
    cp 'I'
    jp z, MoveUp
    cp 'i'
    jp z, MoveUp
    cp 'S'
    jp z, MoveDown
    cp 's'
    jp z, MoveDown
    cp 'K'
    jp z, MoveDown
    cp 'k'
    jp z, MoveDown
    cp 'A'
    jp z, MoveLeft
    cp 'a'
    jp z, MoveLeft
    cp 'J'
    jp z, MoveLeft
    cp 'j'
    jp z, MoveLeft
    cp 'D'
    jp z, MoveRight
    cp 'd'
    jp z, MoveRight
    cp 'L'
    jp z, MoveRight
    cp 'l'
    jp z, MoveRight
    jp MainLoop

ReadJoystick:
    ld a, 1               ; BIOS joystick controller port 1.
    call MSX_GTSTCK
    cp 1
    jp z, MoveUp
    cp 3
    jp z, MoveRight
    cp 5
    jp z, MoveDown
    cp 7
    jp z, MoveLeft
    jp MainLoop

MoveUp:
    ld a, (PlayerY)
    or a
    jp z, DelayInput
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
    jp z, DelayInput
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
DelayInput:
    ld a, 7
    ld (Cooldown), a
    jp MainLoop

TryMove:
    ld a, (CandidateX)
    cp WIDTH
    ret nc
    ld a, (CandidateY)
    cp HEIGHT
    ret nc
    ; HL = MapRAM + CandidateY * WIDTH + CandidateX.
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
    call MSX_BEEP          ; Original mono PSG cue from BIOS.
    jp DrawAgain

CheckHazard:
    cp T_HAZARD
    jr nz, CheckGoal
    ld a, (Health)
    dec a
    ld (Health), a
    or a
    jr nz, DrawAgain
    ld a, 1
    ld (Lost), a
    jp DrawAgain

CheckGoal:
    cp T_EXIT
    jr nz, DrawAgain
    ld a, (GemsLeft)
    or a
    jr nz, DrawAgain
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
DrawAgain:
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

; Screen rendering via genuine MSX BIOS 40x24 text cursor and CHPUT.
Render:
    xor a
    call MSX_CLS
    ld hl, MapRAM
    ld a, 1
    ld (RowCount), a
RenderRow:
    push hl
    ld h, 1
    ld a, (RowCount)
    ld l, a
    call MSX_POSIT
    pop hl
    ld a, WIDTH
    ld (ColCount), a
RenderColumn:
    ld a, (hl)
    push hl
    ld e, a
    ld d, 0
    ld hl, Glyphs
    add hl, de
    ld a, (hl)
    call MSX_CHPUT
    pop hl
    inc hl
    ld a, (ColCount)
    dec a
    ld (ColCount), a
    jr nz, RenderColumn
    ld a, (RowCount)
    inc a
    ld (RowCount), a
    cp HEIGHT+1
    jr nz, RenderRow
    ld h, 0
    ld l, 0
    call MSX_POSIT
    ld hl, Title
    call PrintString
    ld h, 0
    ld l, 22
    call MSX_POSIT
    ld hl, HudLabel
    call PrintString
    ld a, (Level)
    inc a
    add a, '0'
    call MSX_CHPUT
    ld hl, GemLabel
    call PrintString
    ld a, (GemsLeft)
    add a, '0'
    call MSX_CHPUT
    ld hl, HPLabel
    call PrintString
    ld a, (Health)
    add a, '0'
    call MSX_CHPUT
    ld h, 0
    ld l, 23
    call MSX_POSIT
    ld hl, ScoreLabel
    call PrintString
    ld hl, (Score)
    ld de, 1000
    call PrintDigit
    ld de, 100
    call PrintDigit
    ld de, 10
    call PrintDigit
    ld de, 1
    call PrintDigit
    ld h, 15
    ld l, 23
    call MSX_POSIT
    ld hl, ControlLabel
    call PrintString
    ld a, (PlayerX)
    inc a
    ld h, a
    ld a, (PlayerY)
    inc a
    ld l, a
    call MSX_POSIT
    ld a, '@'
    call MSX_CHPUT
    ret

PrintDigit:
    ld c, 0
DigLoop:
    or a
    sbc hl, de
    jr c, DigDone
    inc c
    jr DigLoop
DigDone:
    add hl, de
    ld a, c
    add a, '0'
    push hl
    call MSX_CHPUT
    pop hl
    ret

PrintString:
    ld a, (hl)
    or a
    ret z
    inc hl
    push hl
    call MSX_CHPUT
    pop hl
    jr PrintString

FinalGame:
    ld h, 0
    ld l, 21
    call MSX_POSIT
    ld a, (Won)
    or a
    jr z, ShowDefeat
    ld hl, WinLabel
    jr FinishText
ShowDefeat:
    ld hl, LoseLabel
FinishText:
    call PrintString
    call MSX_BEEP
    call MSX_CHGET
    cp 'r'
    jp z, GameStart
    cp 'R'
    jp z, GameStart
    ret                   ; Return to BASIC on any other key.

Title: db "ORIGINAL MSX STAR ADVENTURE",0
HudLabel: db "LVL:",0
GemLabel: db " GEMS:",0
HPLabel: db " HP:",0
ScoreLabel: db "SCORE:",0
ControlLabel: db "WASD / JOY1  ESC",0
WinLabel: db "YOU WON - ORIGINAL GAME!",0
LoseLabel: db "GAME OVER - PRESS R TO RESTART",0
Glyphs: db '.', '#', '*', '!', '>'
StageMapPointers:
__POINTERS__
StartX: db __START_X__
StartY: db __START_Y__
__LEVEL_MAPS__
GameSignature: db "SKELMSX1"
end
"""
_MAKEFILE = """Z80ASM ?= z80asm
PYTHON ?= python3
.PHONY: all clean
all: build/skeleton-original.rom
build/skeleton-original.bin: game.asm
\tmkdir -p build
\t$(Z80ASM) -o $@ $<
build/skeleton-original.rom: build/skeleton-original.bin
\t$(PYTHON) make_rom.py --code build/skeleton-original.bin --rom $@
clean:
\trm -rf build
"""
_README = """Original MSX1 16KB BIOS-based cartridge. No proprietary firmware included.

Build with z80asm, Python 3 and make. Run:
    make
The artifact build/skeleton-original.rom is a real 0x4000-0x7FFF AB-header
16KB MSX1 cartridge. Uses MSX1 SCREEN 0 (40x24), keyboard and joystick 1.
WASD/IJKL move. ESC quits to MSX BASIC; R restarts after winning or losing.
You must supply a legally obtained/compatible MSX BIOS or your own hardware.
This source is original homebrew, not a licensed commercial game port.
Build validation is not emulator or real-hardware game-play certification.
"""


class MSX1NativeError(ValueError):
    """Original MSX cartridge source does not satisfy target/gameplay/rights constraints."""


@dataclass(frozen=True, slots=True)
class MSX1SourceProject:
    asm: str
    makefile: str
    readme: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_msx1_z80_16kb_bios_rom_source"
    native_rom_built: bool = False
    emulator_gameplay_verified: bool = False
    hardware_tested: bool = False


def compile_native_msx1(
    world: PlayableWorld, rights: HomebrewSource, *, authorized: bool,
) -> MSX1SourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native original MSX1 homebrew requires explicit permission")
    if not isinstance(world, PlayableWorld) or not isinstance(rights, HomebrewSource):
        raise MSX1NativeError("typed original world and rights source required")
    if world.intent.project_id != rights.project_id:
        raise MSX1NativeError("MSX1 generated world and authorship rights do not match")
    if (world.intent.width > MAX_WIDTH or world.intent.height > MAX_HEIGHT
            or len(world.levels) > MAX_LEVELS):
        raise MSX1NativeError("MSX1 40-column SCREEN0 or 16KB cartridge game budget exceeded")
    if world.intent.collectibles_per_level > 9 or world.intent.starting_health > 9:
        raise MSX1NativeError("MSX1 original game HUD requires single-digit health and gem counts")
    win = demonstrate_solvable(world, authorized=True)
    if win.world_digest != world.digest or win.final_state.status != "won":
        raise MSX1NativeError("MSX1 original world lacks valid safe victory replay")
    plan = compile_port(PortRequest((rights,), "msx1", PortMode.REVERSE_CONSTRAINED))
    maps = []
    for stage in world.levels:
        flat = [_TILE_NUM[ch] for row in stage.rows for ch in row]
        if len(flat) != world.intent.width * world.intent.height:
            raise MSX1NativeError("MSX1 source map corrupt or missing original cells")
        maps.append("StageMap" + str(stage.index) + ": db " + ", ".join(str(x) for x in flat))
    replacements = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__POINTERS__": "\n".join("    dw StageMap" + str(n) for n in range(len(world.levels))),
        "__START_X__": ", ".join(str(stage.start[0]) for stage in world.levels),
        "__START_Y__": ", ".join(str(stage.start[1]) for stage in world.levels),
        "__LEVEL_MAPS__": "\n".join(maps),
    }
    asm = _ASM
    for key, text in replacements.items():
        if asm.count(key) != 1:
            raise MSX1NativeError("MSX1 Z80 original source replacement marker collision")
        asm = asm.replace(key, text)
    manifest_json = json.dumps({
        "schema": "skeleton.game_builder.native_msx1_source.v1",
        "target_platform": "msx1",
        "target_format": "MSX1_AB_16KB_BIOS_Z80_CARTRIDGE",
        "source_project_id": rights.project_id,
        "source_platform": rights.platform_id,
        "rights_evidence_sha256": rights.evidence_sha256,
        "original_world_digest": world.digest,
        "world_digest": world.digest,
        "winning_reference_digest": win.digest,
        "target_port_blueprint_digest": plan.digest,
        "load_address": 16384,
        "rom_header": "MSX AB 16bytes",
        "ram_page3_map_base": "C100",
        "screen_mode": "MSX1 40x24 BIOS SCREEN0",
        "input": "MSX BIOS keyboard and joystick1",
        "gameplay_levels": len(world.levels),
        "width": world.intent.width, "height": world.intent.height,
        "original_source_only": True,
        "native_rom_built": False,
        "emulator_gameplay_verified": False,
        "real_msx_hardware_verified": False,
        "distribution_licensed": False,
        "commercial_rom_or_firmware_included": False,
    }, sort_keys=True, indent=2) + "\n"
    digest = sha256((asm+"\0"+_MAKEFILE+"\0"+_README+"\0"+manifest_json).encode()).hexdigest()
    return MSX1SourceProject(asm, _MAKEFILE, _README, manifest_json, digest)


def export_native_msx1(project: MSX1SourceProject, output: str | Path, *, authorized: bool) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("MSX1 source output requires original-homebrew authorization")
    if not isinstance(project, MSX1SourceProject):
        raise MSX1NativeError("typed MSX1 source project required")
    root=Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True, exist_ok=False)
    from .msx1_rom import get_rom_packer_script
    for name, data in (
        ("game.asm",project.asm), ("Makefile",project.makefile),
        ("README.txt",project.readme), ("manifest.json",project.manifest_json),
        ("make_rom.py",get_rom_packer_script()),
    ):
        with (root/name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    return root
