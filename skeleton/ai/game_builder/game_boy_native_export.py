"""Generate an original, *world-derived* Nintendo Game Boy DMG RGBDS cartridge.

Unlike a generic demo ROM, the tilemap, spawn, collectibles, goal, obstacles,
hazards, level progression and safe replay are sourced from a PlayableWorld.
Source generation does not imply ROM compilation, emulator or hardware testing,
license attestation, or release approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

TILE_FLOOR, TILE_WALL, TILE_COLLECTIBLE, TILE_HAZARD, TILE_GOAL, TILE_PLAYER = range(6)
WIDTH_LIMIT = 19
HEIGHT_LIMIT = 17
_ROM_TARGET = "nintendo_game_boy"
_TILE_INDEX = {".": TILE_FLOOR, "S": TILE_FLOOR, "#": TILE_WALL,
               "C": TILE_COLLECTIBLE, "H": TILE_HAZARD, "G": TILE_GOAL}

# Two bitplanes per 8-pixel row. Every tile is original, generated without
# Nintendo character sprites, protected sample assets or a proprietary SDK.
_PIXELS = (
    ("00000000", "00000000", "00100000", "00000000",
     "00000000", "00000010", "00000000", "00000000"),  # floor
    ("33333333", "32222223", "32333323", "32300323",
     "32300323", "32333323", "32222223", "33333333"),  # wall
    ("00011000", "00122100", "01233210", "12333321",
     "12333321", "01233210", "00122100", "00011000"),  # gem
    ("30000003", "03000030", "00300300", "00033000",
     "00033000", "00300300", "03000030", "30000003"),  # hazard
    ("00111100", "01333310", "13000031", "13000031",
     "13000031", "13000031", "01333310", "00111100"),  # gate
    ("00333300", "03122330", "31233213", "32133123",
     "32133123", "31233213", "03122330", "00333300"),  # hero
)

_ASM = r"""; Original homebrew generated from a rights-bound playable world.
; Nintendo Game Boy DMG compatible, RGBDS 1.0 syntax; no commercial ROM data.
DEF rJOYP EQU $FF00
DEF rLCDC EQU $FF40
DEF rLY EQU $FF44
DEF rBGP EQU $FF47
DEF rOBP0 EQU $FF48
DEF rNR52 EQU $FF26
DEF OAM EQU $FE00
DEF TILEMAP EQU $9800
DEF VRAM EQU $8000
DEF BG_BYTE_COUNT EQU 576
DEF LEVEL_COUNT EQU __LEVEL_COUNT__
DEF MAZE_WIDTH EQU __WIDTH__
DEF MAZE_HEIGHT EQU __HEIGHT__
DEF START_HEALTH EQU __HEALTH__
DEF GEMS_PER_LEVEL EQU __GEMS__

SECTION "Cartridge Entry", ROM0[$0100]
    jp Boot
    ds $0150 - @, 0

SECTION "Game Engine", ROM0[$0150]
Boot:
    di
    ld sp, $FFFE
    xor a
    ld [Level], a
    ld [GameWon], a
    ld [GameLost], a
    ld [Score], a
    ld [Cooldown], a
    ld a, START_HEALTH
    ld [Health], a
    call LCDSafe
    xor a
    ldh [rLCDC], a
    ld hl, OAM
    ld bc, 160
.clearOAM:
    xor a
    ld [hli], a
    dec bc
    ld a, b
    or c
    jr nz, .clearOAM
    ld hl, VRAM
    ld de, Tiles
    ld bc, TilesEnd-Tiles
    call CopyBytes
    ld a, $E4
    ldh [rBGP], a
    ldh [rOBP0], a
    ld a, TILE_PLAYER
    ld [OAM+2], a
    xor a
    ld [OAM+3], a
    call LoadLevelWithoutWait
    ld a, $93
    ldh [rLCDC], a

MainLoop:
    call WaitFrame
    ld a, [GameWon]
    or a
    jr nz, .win
    ld a, [GameLost]
    or a
    jr nz, .loss
    call PollDpad
    call DrawPlayer
    jp MainLoop
.win:
    ld a, $1B
    ldh [rOBP0], a
    call DrawPlayer
    jp MainLoop
.loss:
    xor a
    ldh [rOBP0], a
    call DrawPlayer
    jp MainLoop

; Calls occur during VBlank; never write the enabled LCD tilemap in mode 3.
WaitFrame:
    ldh a, [rLY]
    cp 144
    jr nc, WaitFrame
.wait:
    ldh a, [rLY]
    cp 144
    jr c, .wait
    ret

LCDSafe:
    ldh a, [rLCDC]
    bit 7, a
    ret z
.wait:
    ldh a, [rLY]
    cp 144
    jr c, .wait
    ret

CopyBytes:
    ld a, b
    or c
    ret z
.copy:
    ld a, [de]
    ld [hli], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .copy
    ret

LoadLevel:
    call LCDSafe
    xor a
    ldh [rLCDC], a
    call LoadLevelWithoutWait
    ld a, $93
    ldh [rLCDC], a
    ret

LoadLevelWithoutWait:
    ld a, GEMS_PER_LEVEL
    ld [GemsRemaining], a
    ld a, [Level]
    ld e, a
    ld d, 0
    ld hl, StartXTable
    add hl, de
    ld a, [hl]
    ld [PlayerX], a
    ld hl, StartYTable
    add hl, de
    ld a, [hl]
    ld [PlayerY], a
    ld a, [Level]
    add a
    ld e, a
    ld d, 0
    ld hl, LevelMapPointers
    add hl, de
    ld a, [hli]
    ld e, a
    ld a, [hl]
    ld d, a
    ld hl, TILEMAP
    ld bc, BG_BYTE_COUNT
    call CopyBytes
    ret

DrawPlayer:
    ld a, [PlayerY]
    add a
    add a
    add a
    add 16
    ld [OAM], a
    ld a, [PlayerX]
    add a
    add a
    add a
    add 8
    ld [OAM+1], a
    ret

PollDpad:
    ld a, [Cooldown]
    or a
    jr z, .poll
    dec a
    ld [Cooldown], a
    ret
.poll:
    ld a, $20
    ldh [rJOYP], a
    ldh a, [rJOYP]
    ldh a, [rJOYP]
    cpl
    and $0F
    ld b, a
    ld a, $30
    ldh [rJOYP], a
    bit 0, b
    jp nz, MoveRight
    bit 1, b
    jp nz, MoveLeft
    bit 2, b
    jp nz, MoveUp
    bit 3, b
    jp nz, MoveDown
    ret

MoveRight:
    ld a, [PlayerX]
    inc a
    ld [NextX], a
    ld a, [PlayerY]
    ld [NextY], a
    jp TryMove
MoveLeft:
    ld a, [PlayerX]
    dec a
    ld [NextX], a
    ld a, [PlayerY]
    ld [NextY], a
    jp TryMove
MoveUp:
    ld a, [PlayerY]
    dec a
    ld [NextY], a
    ld a, [PlayerX]
    ld [NextX], a
    jp TryMove
MoveDown:
    ld a, [PlayerY]
    inc a
    ld [NextY], a
    ld a, [PlayerX]
    ld [NextX], a
    jp TryMove

TryMove:
    ld a, 7
    ld [Cooldown], a
    ld a, [NextX]
    cp MAZE_WIDTH
    ret nc
    ld a, [NextY]
    cp MAZE_HEIGHT
    ret nc
    ; BG tilemap is a 32-byte stride even when the maze is narrower.
    ld a, [NextY]
    ld b, a
    ld hl, TILEMAP
.row:
    ld a, b
    or a
    jr z, .column
    ld de, 32
    add hl, de
    dec b
    jr .row
.column:
    ld a, [NextX]
    ld e, a
    ld d, 0
    add hl, de
    ld a, [hl]
    cp TILE_WALL
    ret z
    push af
    ld a, [NextX]
    ld [PlayerX], a
    ld a, [NextY]
    ld [PlayerY], a
    pop af
    cp TILE_COLLECTIBLE
    jr nz, .notGem
    xor a
    ld [hl], a
    ld a, [GemsRemaining]
    dec a
    ld [GemsRemaining], a
    ld a, [Score]
    inc a
    ld [Score], a
    ret
.notGem:
    cp TILE_HAZARD
    jr nz, .notHazard
    ld a, [Health]
    dec a
    ld [Health], a
    ret nz
    ld a, 1
    ld [GameLost], a
    ret
.notHazard:
    cp TILE_GOAL
    ret nz
    ld a, [GemsRemaining]
    or a
    ret nz
    ld a, [Level]
    inc a
    cp LEVEL_COUNT
    jr c, .nextLevel
    ld a, 1
    ld [GameWon], a
    ret
.nextLevel:
    ld [Level], a
    call LoadLevel
    ret

SECTION "Pixel Art", ROM0
Tiles:
__TILE_BYTES__
TilesEnd:

SECTION "Game Maps", ROM0
LevelMapPointers:
__MAP_POINTERS__
StartXTable:
__START_X__
StartYTable:
__START_Y__
__MAP_DATA__

SECTION "Game State", WRAM0
Level: ds 1
PlayerX: ds 1
PlayerY: ds 1
NextX: ds 1
NextY: ds 1
Cooldown: ds 1
Health: ds 1
Score: ds 1
GemsRemaining: ds 1
GameWon: ds 1
GameLost: ds 1
"""

_MAKEFILE = """RGBASM ?= rgbasm
RGBLINK ?= rgblink
RGBFIX ?= rgbfix
.PHONY: all clean
all: build/skeleton-original.gb
build/skeleton.o: main.asm
\tmkdir -p build
\t$(RGBASM) -o $@ $<
build/skeleton-original.gb: build/skeleton.o
\t$(RGBLINK) -o $@ $<
\t$(RGBFIX) -v -p 0 -t SKELORIG $@
clean:
\trm -rf build
"""


class GameBoySourceError(ValueError):
    """World or rights source cannot be emitted as a DMG homebrew cartridge."""


@dataclass(frozen=True, slots=True)
class GameBoySourceProject:
    asm: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "game_boy_dmg_rgbds_source"
    rom_compiled: bool = False
    emulator_verified: bool = False
    hardware_verified: bool = False


def _tile_bytes() -> str:
    lines: list[str] = []
    for index, image in enumerate(_PIXELS):
        lines.append(f"; original tile {index}")
        for row in image:
            if len(row) != 8 or set(row) - set("0123"):
                raise GameBoySourceError("invalid source tile graphics")
            lo = sum((int(px) & 1) << (7 - n) for n, px in enumerate(row))
            hi = sum(((int(px) >> 1) & 1) << (7 - n) for n, px in enumerate(row))
            lines.append(f"    db ${lo:02X}, ${hi:02X}".replace("\$", "$"))
    return "\n".join(lines)


def compile_native_game_boy(
    world: PlayableWorld, source: HomebrewSource, *, authorized: bool,
) -> GameBoySourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Game Boy native homebrew export needs explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise GameBoySourceError("typed original world and rights-bound source required")
    if source.project_id != world.intent.project_id:
        raise GameBoySourceError("world and clearance project mismatch")
    if not 1 <= world.intent.width <= WIDTH_LIMIT or not 1 <= world.intent.height <= HEIGHT_LIMIT:
        raise GameBoySourceError("world exceeds DMG 20x18 visible tile budget")
    if len(world.levels) > 8:
        raise GameBoySourceError("DMG source level count exceeds bounded bankless engine")
    blueprint = compile_port(PortRequest((source,), _ROM_TARGET, PortMode.REVERSE_CONSTRAINED))
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise GameBoySourceError("no deterministic safe-winning reference replay")

    tables: list[str] = []
    for level in world.levels:
        rows = []
        for row in level.rows:
            tiles = [_TILE_INDEX[char] for char in row]
            tiles.extend([TILE_FLOOR] * (32 - len(tiles)))
            rows.append("    db " + ", ".join(f"${tile:02X}".replace("\$", "$") for tile in tiles))
        for _ in range(18 - len(level.rows)):
            rows.append("    ds 32, 0")
        tables.append(f"LevelMap{level.index}:\n" + "\n".join(rows))
    tokens = {
        "__LEVEL_COUNT__": str(len(world.levels)),
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__HEALTH__": str(world.intent.starting_health),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__TILE_BYTES__": _tile_bytes(),
        "__MAP_POINTERS__": "\n".join(f"    dw LevelMap{i}" for i in range(len(world.levels))),
        "__START_X__": "    db " + ", ".join(str(level.start[0]) for level in world.levels),
        "__START_Y__": "    db " + ", ".join(str(level.start[1]) for level in world.levels),
        "__MAP_DATA__": "\n\n".join(tables),
    }
    asm = _ASM
    for marker, value in tokens.items():
        if asm.count(marker) != 1:
            raise GameBoySourceError("source template marker contract violated")
        asm = asm.replace(marker, value)
    asm += "\n"
    manifest = {
        "schema": "skeleton.game_builder.game_boy_native_source.v1",
        "platform": _ROM_TARGET,
        "source_platform": source.platform_id,
        "project_id": source.project_id,
        "rights_reference_sha256": source.evidence_sha256,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "blueprint_digest": blueprint.digest,
        "engine": "original_dmg_2bpp_tile_maze.v1",
        "artwork": "original_programmatic_tiles",
        "levels": len(world.levels),
        "width": world.intent.width,
        "height": world.intent.height,
        "safe_reference_moves": sum(len(level.safe_solution) for level in world.levels),
        "sdk": "RGBDS_1.0_open_homebrew",
        "rom_compiled": False,
        "emulator_verified": False,
        "physical_hardware_verified": False,
        "release_approved": False,
        "licensed_distribution": False,
    }
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    digest = sha256((asm + "\0" + _MAKEFILE + "\0" + manifest_json).encode()).hexdigest()
    return GameBoySourceProject(asm, _MAKEFILE, manifest_json, digest)


def export_native_game_boy(
    project: GameBoySourceProject, output: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native GB source export needs explicit authorization")
    if not isinstance(project, GameBoySourceProject):
        raise GameBoySourceError("typed Game Boy project required")
    folder = Path(output)
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(str(folder))
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("main.asm", project.asm), ("Makefile", project.makefile),
        ("manifest.json", project.manifest_json),
    ):
        with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    return folder
