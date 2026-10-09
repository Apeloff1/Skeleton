"""Authentic original 48K Sinclair ZX Spectrum Z80 game (tape CODE format).

Produces z80asm source assembled at 32768 with ROM RST $10 screen output,
48K ULA keyboard-row port reads, original map/maze mechanics and an original
beeper/border cue. Native game is packaged as genuine Spectrum .TAP CODE
blocks by a separate provenance-bound offline tape packer. No ROM, emulator,
or commercial game contents are distributed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH = 29
MAX_HEIGHT = 21
MAX_LEVELS = 8
_TILES = {".":0,"S":0,"#":1,"C":2,"H":3,"G":4}

_ASM = r"""; Fully original Sinclair Spectrum 48K Z80 maze game.
; Assemble: z80asm -o skeleton-original.bin game.asm
; BASIC: CLEAR 32767 : LOAD "" CODE : RANDOMIZE USR 32768
org 32768

WIDTH: equ __WIDTH__
HEIGHT: equ __HEIGHT__
LEVELS: equ __LEVELS__
GEMS: equ __GEMS__
FIRST_HEALTH: equ __HEALTH__
CELLS: equ WIDTH * HEIGHT
T_WALL: equ 1
T_GEM: equ 2
T_HAZARD: equ 3
T_EXIT: equ 4

Start:
    ei
    xor a
    out (254), a           ; Genuine ZX ULA border and beeper output.
    ld (level), a
    ld (won), a
    ld (lost), a
    ld (score), a
    ld (score+1), a
    ld a, FIRST_HEALTH
    ld (health), a
    call LoadLevel
MainLoop:
    halt                   ; Interrupt-synchronized original Spectrum frame.
    ld a, (won)
    or a
    jp nz, Finish
    ld a, (lost)
    or a
    jp nz, Finish
    ld a, (cooldown)
    or a
    jr z, ScanKeyboard
    dec a
    ld (cooldown), a
    jp MainLoop

ScanKeyboard:
    ; Real ZX keyboard matrix, active-low. Q/W = row FBFE,
    ; A/S/D = row FDFE. The low address byte FE selects the ULA.
    ld bc, 0FBFEh
    in a, (c)
    bit 0, a               ; Q = exit from BASIC USR invocation.
    ret z
    bit 1, a               ; W = up.
    jp z, MoveUp
    ld bc, 0FDFEh
    in a, (c)
    bit 0, a
    jp z, MoveLeft
    bit 1, a
    jp z, MoveDown
    bit 2, a
    jp z, MoveRight
    jp MainLoop

MoveUp:
    ld a, (player_y)
    or a
    jp z, DelayMove
    dec a
    ld (candidate_y), a
    ld a, (player_x)
    ld (candidate_x), a
    jp CommitMove
MoveDown:
    ld a, (player_y)
    inc a
    ld (candidate_y), a
    ld a, (player_x)
    ld (candidate_x), a
    jp CommitMove
MoveLeft:
    ld a, (player_x)
    or a
    jp z, DelayMove
    dec a
    ld (candidate_x), a
    ld a, (player_y)
    ld (candidate_y), a
    jp CommitMove
MoveRight:
    ld a, (player_x)
    inc a
    ld (candidate_x), a
    ld a, (player_y)
    ld (candidate_y), a

CommitMove:
    call TryMove
DelayMove:
    ld a, 7
    ld (cooldown), a
    jp MainLoop

; Each temporary state and tile is read from guest RAM; no host-side cheats.
TryMove:
    ld a, (candidate_x)
    cp WIDTH
    ret nc
    ld a, (candidate_y)
    cp HEIGHT
    ret nc
    ; HL = guest RAM address MapRAM + y*WIDTH + x.
    ld hl, 0
    ld de, WIDTH
    ld a, (candidate_y)
    or a
    jr z, AddX
MultiplyY:
    add hl, de
    dec a
    jr nz, MultiplyY
AddX:
    ld a, (candidate_x)
    ld e, a
    ld d, 0
    add hl, de
    ld de, MapRAM
    add hl, de
    ld a, (hl)
    ld (last_tile), a
    cp T_WALL
    ret z
    ld a, (candidate_x)
    ld (player_x), a
    ld a, (candidate_y)
    ld (player_y), a
    ld a, (last_tile)
    cp T_GEM
    jr nz, CheckHazard
    xor a
    ld (hl), a
    ld a, (gems_left)
    dec a
    ld (gems_left), a
    ld hl, (score)
    ld de, 10
    add hl, de
    ld (score), hl
    ld a, 16               ; Original Spectrum border and beeper cue.
    out (254), a
    jr Redraw
CheckHazard:
    cp T_HAZARD
    jr nz, CheckExit
    ld a, (health)
    dec a
    ld (health), a
    or a
    jr nz, Redraw
    ld a, 1
    ld (lost), a
    jr Redraw
CheckExit:
    cp T_EXIT
    jr nz, Redraw
    ld a, (gems_left)
    or a
    jr nz, Redraw
    ld hl, (score)
    ld de, 100
    add hl, de
    ld (score), hl
    ld a, (level)
    inc a
    cp LEVELS
    jr z, WinGame
    ld (level), a
    call LoadLevel
    ret
WinGame:
    ld a, 1
    ld (won), a
Redraw:
    call Render
    ret

LoadLevel:
    ld a, GEMS
    ld (gems_left), a
    xor a
    ld (cooldown), a
    ld a, (level)
    ld e, a
    ld d, 0
    ld hl, StartX
    add hl, de
    ld a, (hl)
    ld (player_x), a
    ld hl, StartY
    add hl, de
    ld a, (hl)
    ld (player_y), a
    ld hl, LevelPointers
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

; RST $10 is the ZX Spectrum 48K ROM character-output entry.
; ROM firmware is executed by the machine but never bundled in our source.
PrintCharacter:
    push bc
    push de
    push hl
    rst 10h
    pop hl
    pop de
    pop bc
    ret

PrintAt:
    ; Input B = row, C = column. Print ZX control 22, y, x.
    ld a, 22
    call PrintCharacter
    ld a, b
    call PrintCharacter
    ld a, c
    call PrintCharacter
    ret

Render:
    ; ZX ROM CLS, screen pixels $4000 and attributes $5800.
    call 0DAFh
    ld hl, MapRAM
    xor a
    ld (render_y), a
RenderRow:
    ld b, 0
    ld a, (render_y)
    inc a
    ld b, a
    ld c, 1
    call PrintAt
    ld a, WIDTH
    ld (render_x), a
RenderCol:
    ld a, (hl)
    push hl
    ld e, a
    ld d, 0
    ld hl, TileGlyphs
    add hl, de
    ld a, (hl)
    call PrintCharacter
    pop hl
    inc hl
    ld a, (render_x)
    dec a
    ld (render_x), a
    jr nz, RenderCol
    ld a, (render_y)
    inc a
    ld (render_y), a
    cp HEIGHT
    jr nz, RenderRow
    ld b, 0
    ld c, 0
    call PrintAt
    ld hl, Banner
    call PrintString
    ld b, 22
    ld c, 0
    call PrintAt
    ld hl, HUD
    call PrintString
    ld a, (level)
    inc a
    add a, '0'
    call PrintCharacter
    ld hl, GemsLabel
    call PrintString
    ld a, (gems_left)
    add a, '0'
    call PrintCharacter
    ld hl, HealthLabel
    call PrintString
    ld a, (health)
    add a, '0'
    call PrintCharacter
    ld b, 23
    ld c, 0
    call PrintAt
    ld hl, ScoreLabel
    call PrintString
    ld hl, (score)
    ld de, 1000
    call PrintDecimalDigit
    ld de, 100
    call PrintDecimalDigit
    ld de, 10
    call PrintDecimalDigit
    ld de, 1
    call PrintDecimalDigit
    ld b, 23
    ld c, 13
    call PrintAt
    ld hl, InputLabel
    call PrintString
    ld a, (player_y)
    inc a
    ld b, a
    ld a, (player_x)
    inc a
    ld c, a
    call PrintAt
    ld a, '@'
    call PrintCharacter
    ret

PrintString:
    ld a, (hl)
    or a
    ret z
    inc hl
    call PrintCharacter
    jr PrintString

PrintDecimalDigit:
    ld c, 0
DecimalLoop:
    or a
    sbc hl, de
    jr c, DecimalDone
    inc c
    jr DecimalLoop
DecimalDone:
    add hl, de
    ld a, c
    add a, '0'
    call PrintCharacter
    ret

Finish:
    ld b, 21
    ld c, 0
    call PrintAt
    ld a, (won)
    or a
    jr z, LosingMessage
    ld hl, VictoryMessage
    jr PrintFinish
LosingMessage:
    ld hl, LossMessage
PrintFinish:
    call PrintString
    xor a
    out (254), a
    ret                     ; Return cleanly to Spectrum BASIC after USR.

Banner: db "ORIGINAL ZX SPECTRUM STAR MAZE",0
HUD: db "LVL:",0
GemsLabel: db " GEMS:",0
HealthLabel: db " HP:",0
ScoreLabel: db "SCORE:",0
InputLabel: db "WASD Q=EXIT",0
VictoryMessage: db "VICTORY - ORIGINAL GAME!",0
LossMessage: db "GAME OVER - PRESS Q",0
TileGlyphs: db '.', '#', '*', '!', 'E'
LevelPointers:
__POINTERS__
StartX: db __START_X__
StartY: db __START_Y__
__MAP_DATA__

level: db 0
player_x: db 0
player_y: db 0
candidate_x: db 0
candidate_y: db 0
gems_left: db 0
health: db 0
won: db 0
lost: db 0
score: dw 0
cooldown: db 0
render_x: db 0
render_y: db 0
last_tile: db 0
MapRAM: ds CELLS, 0
GameSignature: db "SKELZX48"
end
"""
_MAKEFILE = """Z80ASM ?= z80asm
PYTHON ?= python3
.PHONY: all clean
all: build/skeleton-original.tap
build/skeleton-original.bin: game.asm
\tmkdir -p build
\t$(Z80ASM) -o $@ $<
build/skeleton-original.tap: build/skeleton-original.bin
\t$(PYTHON) make_tap.py --code build/skeleton-original.bin --tap $@
clean:
\trm -rf build
"""
_README = """Original ZX Spectrum 48K maze homebrew, generated by Skeleton.
Requires an original ZX Spectrum-compatible ROM on the user's machine/emulator.
No commercial ROM, copied commercial game, firmware or third-party asset included.

Build: make (requires z80asm and Python 3).
Output: build/skeleton-original.bin and build/skeleton-original.tap.

The .TAP is a standard CODE-only tape block (not an autostart BASIC program).
Use a Spectrum 48K BASIC terminal to load and run the game:
  CLEAR 32767
  LOAD "" CODE
  RANDOMIZE USR 32768
Controls: W up, A left, S down, D right, Q exit.
Do not overwrite, distribute, or claim hardware verification without independent checks.
"""


class SpectrumNativeError(ValueError):
    """Original ZX Spectrum program violates machine budget, identity or rights."""


@dataclass(frozen=True, slots=True)
class SpectrumSourceProject:
    asm: str
    makefile: str
    readme: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_spectrum_48k_z80_tap_source"
    binary_compiled: bool = False
    emulator_verified: bool = False
    physical_hardware_verified: bool = False


def compile_native_spectrum(
    world: PlayableWorld, rights: HomebrewSource, *, authorized: bool,
) -> SpectrumSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("original ZX Spectrum native export requires authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(rights, HomebrewSource):
        raise SpectrumNativeError("typed original authored world and rights source required")
    if world.intent.project_id != rights.project_id:
        raise SpectrumNativeError("Spectrum game world and rights evidence project mismatch")
    if (world.intent.width > MAX_WIDTH or world.intent.height > MAX_HEIGHT
            or len(world.levels) > MAX_LEVELS):
        raise SpectrumNativeError("Spectrum 32x24 text renderer or original stage budget exceeded")
    if world.intent.collectibles_per_level > 9 or world.intent.starting_health > 9:
        raise SpectrumNativeError("Spectrum ROM text HUD counter budget exceeded")
    proof = demonstrate_solvable(world, authorized=True)
    if proof.world_digest != world.digest or proof.final_state.status != "won":
        raise SpectrumNativeError("unproven original game cannot be exported")
    plan = compile_port(PortRequest((rights,), "sinclair_zx_spectrum", PortMode.REVERSE_CONSTRAINED))
    maps = []
    for stage in world.levels:
        tiles = [_TILES[ch] for row in stage.rows for ch in row]
        if len(tiles) != world.intent.width * world.intent.height:
            raise SpectrumNativeError("malformed original ZX gameplay geometry")
        maps.append("LevelMap" + str(stage.index) + ": db " + ", ".join(str(x) for x in tiles))
    substitutions = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__POINTERS__": "\n".join("    dw LevelMap" + str(x) for x in range(len(world.levels))),
        "__START_X__": ", ".join(str(s.start[0]) for s in world.levels),
        "__START_Y__": ", ".join(str(s.start[1]) for s in world.levels),
        "__MAP_DATA__": "\n".join(maps),
    }
    program = _ASM
    for marker, value in substitutions.items():
        if program.count(marker) != 1:
            raise SpectrumNativeError("native Spectrum 48K program placeholder collision")
        program = program.replace(marker, value)
    manifest = json.dumps({
        "schema": "skeleton.game_builder.spectrum_native_source.v1",
        "target_platform_id": "sinclair_zx_spectrum",
        "target_format": "ZX_48K_Z80_CODE_TAP",
        "load_address": 32768, "screen": "ZX_ULA_ROM_32x24_text",
        "inputs": "ZX_ULA_keyboard_matrix_WASD_Q",
        "gameplay_world_digest": world.digest,
        "world_digest": world.digest,
        "winning_reference_digest": proof.digest,
        "project_id": rights.project_id,
        "original_rights_evidence_sha256": rights.evidence_sha256,
        "source_basis": rights.platform_id,
        "port_plan_digest": plan.digest,
        "levels": len(world.levels),
        "width": world.intent.width, "height": world.intent.height,
        "safe_actions": sum(len(level.safe_solution) for level in world.levels),
        "native_binary_compiled": False, "tape_packaged": False,
        "emulator_playthrough_verified": False,
        "hardware_verified": False, "distribution_licensed": False,
        "third_party_rom_included": False,
    }, sort_keys=True, indent=2) + "\n"
    digest = sha256((program + "\0" + _MAKEFILE + "\0" + _README + "\0" + manifest).encode()).hexdigest()
    return SpectrumSourceProject(program, _MAKEFILE, _README, manifest, digest)


def export_native_spectrum(
    project: SpectrumSourceProject, output: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("original Spectrum source export requires authorization")
    if not isinstance(project, SpectrumSourceProject):
        raise SpectrumNativeError("typed Spectrum Z80 game project required")
    root = Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("game.asm", project.asm), ("Makefile", project.makefile),
        ("README.txt", project.readme), ("manifest.json", project.manifest_json),
    ):
        with (root / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    # Offline, deterministic machine-native TAP packaging script, imported
    # from a single audited canonical copy; no network or proprietary image.
    from .spectrum_tap import get_tape_packer_script
    with (root / "make_tap.py").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(get_tape_packer_script())
    return root
