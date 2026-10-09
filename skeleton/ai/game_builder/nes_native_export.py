"""Original PlayableWorld -> genuine NES NROM-256 6502/2bpp cartridge source.

World tiles are translated into a 32x30 NES name table, copied to CPU RAM and
the PPU. The playable machine code handles D-pad input, collisions, collectibles,
hazards, lives, level changes, and win/loss state. Not a commercial ROM clone.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .game_boy_native_export import _PIXELS, _TILE_INDEX
from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

_MAX_WIDTH, _MAX_HEIGHT = 31, 29

_ASM = r"""; Original world-specific NES NROM-256 homebrew, ca65/ld65.
.segment "HEADER"
.byte "NES", $1A, 2, 1, 0, 0
.res 8, 0

.segment "ZEROPAGE"
Level: .res 1
PlayerX: .res 1
PlayerY: .res 1
NextX: .res 1
NextY: .res 1
Health: .res 1
Score: .res 1
GemsRemaining: .res 1
GameWon: .res 1
GameLost: .res 1
Cooldown: .res 1
PadUp: .res 1
PadDown: .res 1
PadLeft: .res 1
PadRight: .res 1
MapPtr: .res 2
WorkPtr: .res 2
CalcPtr: .res 2

; $0200-$02FF is hardware sprite DMA page.
; $0300-$06BF is a deterministic 960-byte shadow name table.
.segment "CODE"
MAZE_WIDTH = __WIDTH__
MAZE_HEIGHT = __HEIGHT__
LEVEL_COUNT = __LEVEL_COUNT__
GEMS_PER_LEVEL = __GEMS__
START_HEALTH = __HEALTH__
MAP_RAM = $0300

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
@wait1:
    bit $2002
    bpl @wait1
    ldx #0
    lda #$FF
@clearSprites:
    sta $0200,x
    inx
    bne @clearSprites
@wait2:
    bit $2002
    bpl @wait2
    lda #0
    sta Level
    sta GameWon
    sta GameLost
    sta Score
    sta Cooldown
    lda #START_HEALTH
    sta Health
    jsr UploadPalette
    jsr LoadLevel
    lda #$00
    sta $2000
    lda #$1E
    sta $2001

MainLoop:
    jsr WaitFrame
    jsr PollPad
    jsr UpdateSprite
    lda #$00
    sta $2003
    lda #$02
    sta $4014
    jmp MainLoop

WaitFrame:
@off:
    bit $2002
    bmi @off
@on:
    bit $2002
    bpl @on
    rts

UploadPalette:
    lda $2002
    lda #$3F
    sta $2006
    lda #0
    sta $2006
    ldx #0
@loop:
    lda Colors,x
    sta $2007
    inx
    cpx #32
    bne @loop
    rts

LoadLevel:
    lda #0
    sta $2001
    lda #GEMS_PER_LEVEL
    sta GemsRemaining
    ldx Level
    lda SpawnXs,x
    sta PlayerX
    lda SpawnYs,x
    sta PlayerY
    txa
    asl a
    tax
    lda LevelPtrs,x
    sta MapPtr
    lda LevelPtrs+1,x
    sta MapPtr+1
    lda #<MAP_RAM
    sta WorkPtr
    lda #>MAP_RAM
    sta WorkPtr+1
    ldx #3
@copyPages:
    ldy #0
@copyFull:
    lda (MapPtr),y
    sta (WorkPtr),y
    iny
    bne @copyFull
    inc MapPtr+1
    inc WorkPtr+1
    dex
    bne @copyPages
    ldy #0
@copyTail:
    lda (MapPtr),y
    sta (WorkPtr),y
    iny
    cpy #192
    bne @copyTail
    ; Copy the independent RAM map into PPU background name table.
    lda $2002
    lda #$20
    sta $2006
    lda #0
    sta $2006
    lda #<MAP_RAM
    sta WorkPtr
    lda #>MAP_RAM
    sta WorkPtr+1
    ldx #3
@ppuPages:
    ldy #0
@ppuFull:
    lda (WorkPtr),y
    sta $2007
    iny
    bne @ppuFull
    inc WorkPtr+1
    dex
    bne @ppuPages
    ldy #0
@ppuTail:
    lda (WorkPtr),y
    sta $2007
    iny
    cpy #192
    bne @ppuTail
    ldx #64
    lda #0
@attr:
    sta $2007
    dex
    bne @attr
    lda #0
    sta $2005
    sta $2005
    lda #$1E
    sta $2001
    rts

UpdateSprite:
    lda PlayerY
    asl a
    asl a
    asl a
    sec
    sbc #1
    sta $0200
    lda PlayerX
    asl a
    asl a
    asl a
    sta $0203
    lda #0
    sta $0202
    lda #5
    ldx GameWon
    beq @notWon
    lda #4
@notWon:
    ldx GameLost
    beq @notLost
    lda #3
@notLost:
    sta $0201
    rts

PollPad:
    lda #1
    sta $4016
    lda #0
    sta $4016
    ldx #4
@skipButtons:
    lda $4016
    dex
    bne @skipButtons
    lda $4016
    and #1
    sta PadUp
    lda $4016
    and #1
    sta PadDown
    lda $4016
    and #1
    sta PadLeft
    lda $4016
    and #1
    sta PadRight
    lda GameWon
    ora GameLost
    bne @done
    lda Cooldown
    beq @ready
    dec Cooldown
    rts
@ready:
    lda PadUp
    beq @down
    jmp MoveUp
@down:
    lda PadDown
    beq @left
    jmp MoveDown
@left:
    lda PadLeft
    beq @right
    jmp MoveLeft
@right:
    lda PadRight
    beq @done
    jmp MoveRight
@done:
    rts

MoveUp:
    lda PlayerY
    sec
    sbc #1
    sta NextY
    lda PlayerX
    sta NextX
    jmp TryMove
MoveDown:
    lda PlayerY
    clc
    adc #1
    sta NextY
    lda PlayerX
    sta NextX
    jmp TryMove
MoveLeft:
    lda PlayerX
    sec
    sbc #1
    sta NextX
    lda PlayerY
    sta NextY
    jmp TryMove
MoveRight:
    lda PlayerX
    clc
    adc #1
    sta NextX
    lda PlayerY
    sta NextY

TryMove:
    lda #7
    sta Cooldown
    lda NextX
    cmp #MAZE_WIDTH
    bcc @xInside
    rts
@xInside:
    lda NextY
    cmp #MAZE_HEIGHT
    bcc @yInside
    rts
@yInside:
    lda NextY
    sta CalcPtr
    lda #0
    sta CalcPtr+1
    ldx #5
@shift:
    asl CalcPtr
    rol CalcPtr+1
    dex
    bne @shift
    clc
    lda CalcPtr
    adc NextX
    sta CalcPtr
    lda CalcPtr+1
    adc #>MAP_RAM
    sta CalcPtr+1
    ldy #0
    lda (CalcPtr),y
    cmp #1
    beq @blocked
    sta PadUp
    lda NextX
    sta PlayerX
    lda NextY
    sta PlayerY
    lda PadUp
    cmp #2
    bne @hazard
    lda #0
    sta (CalcPtr),y
    jsr EraseGemTile
    dec GemsRemaining
    inc Score
    rts
@hazard:
    cmp #3
    bne @goal
    dec Health
    bne @blocked
    lda #1
    sta GameLost
    rts
@goal:
    cmp #4
    bne @blocked
    lda GemsRemaining
    bne @blocked
    inc Level
    lda Level
    cmp #LEVEL_COUNT
    bcc @next
    lda #1
    sta GameWon
    rts
@next:
    jsr LoadLevel
@blocked:
    rts

EraseGemTile:
    lda $2002
    clc
    lda CalcPtr+1
    adc #$1D
    sta $2006
    lda CalcPtr
    sta $2006
    lda #0
    sta $2007
    lda #0
    sta $2005
    sta $2005
    rts

Colors:
.byte $0F,$30,$16,$26, $0F,$30,$10,$20, $0F,$30,$00,$10, $0F,$30,$06,$16
.byte $0F,$30,$16,$26, $0F,$30,$21,$11, $0F,$30,$06,$16, $0F,$30,$16,$26

LevelPtrs:
__POINTERS__
SpawnXs:
__START_X__
SpawnYs:
__START_Y__
__MAPS__

NMI:
    rti
IRQ:
    rti

.segment "VECTORS"
.addr NMI, Reset, IRQ

.segment "CHARS"
Tiles:
__TILES__
TilesEnd:
.res $2000 - (TilesEnd - Tiles), 0
"""

_LINKER = """MEMORY {
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
_MAKEFILE = """CA65 ?= ca65
LD65 ?= ld65
.PHONY: all clean
all: build/skeleton-original.nes
build/skeleton.o: main.s
\tmkdir -p build
\t$(CA65) -o $@ $<
build/skeleton-original.nes: build/skeleton.o nes.cfg
\t$(LD65) -C nes.cfg -o $@ $<
clean:
\trm -rf build
"""


class NativeNESError(ValueError):
    """A requested original game cannot target this NES NROM hardware budget."""


@dataclass(frozen=True, slots=True)
class NativeNESSourceProject:
    asm: str
    linker_cfg: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "nes_nrom256_ca65_original_game_source"
    cartridge_built: bool = False
    emulator_verified: bool = False
    hardware_verified: bool = False


def _nes_chr() -> str:
    lines = []
    for index, image in enumerate(_PIXELS):
        lo, hi = [], []
        for row in image:
            lo.append(sum((int(ch) & 1) << (7 - i) for i, ch in enumerate(row)))
            hi.append(sum((int(ch) >> 1) << (7 - i) for i, ch in enumerate(row)))
        lines.append(f"; original two-plane NES tile {index}")
        for bank in (lo, hi):
            lines.append(".byte " + ", ".join(f"$%02X" % v for v in bank))
    return "\n".join(lines)


def compile_native_nes(
    world: PlayableWorld, source: HomebrewSource, *, authorized: bool,
) -> NativeNESSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native NES homebrew source needs explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise NativeNESError("typed world and cleared original source required")
    if world.intent.project_id != source.project_id:
        raise NativeNESError("world/source project mismatch")
    if world.intent.width > _MAX_WIDTH or world.intent.height > _MAX_HEIGHT:
        raise NativeNESError("NES background tile envelope exceeded")
    blueprint = compile_port(PortRequest((source,), "nintendo_famicom", PortMode.REVERSE_CONSTRAINED))
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise NativeNESError("no safe-winning deterministic game replay")

    maps = []
    for level in world.levels:
        rows = []
        for row in level.rows:
            tiles = [_TILE_INDEX[tile] for tile in row] + [0] * (32 - len(row))
            rows.append(".byte " + ", ".join(str(tile) for tile in tiles))
        for _ in range(30 - len(level.rows)):
            rows.append(".res 32, 0")
        maps.append(f"LevelMap{level.index}:\n" + "\n".join(rows))
    substitutions = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVEL_COUNT__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__POINTERS__": "\n".join(f".addr LevelMap{i}" for i in range(len(world.levels))),
        "__START_X__": ".byte " + ", ".join(str(level.start[0]) for level in world.levels),
        "__START_Y__": ".byte " + ", ".join(str(level.start[1]) for level in world.levels),
        "__MAPS__": "\n\n".join(maps),
        "__TILES__": _nes_chr(),
    }
    result = _ASM
    for marker, value in substitutions.items():
        if result.count(marker) != 1:
            raise NativeNESError("template marker collision")
        result = result.replace(marker, value)
    asm = result + "\n"
    manifest = {
        "schema": "skeleton.game_builder.native_nes_source.v1",
        "project_id": source.project_id,
        "source_platform": source.platform_id,
        "rights_reference_sha256": source.evidence_sha256,
        "target": "nintendo_famicom",
        "format": "ines_nrom256_mapper0",
        "original_artwork_only": True,
        "world_digest": world.digest,
        "safe_replay_digest": replay.digest,
        "blueprint_digest": blueprint.digest,
        "levels": len(world.levels),
        "width": world.intent.width,
        "height": world.intent.height,
        "reference_safe_moves": sum(len(level.safe_solution) for level in world.levels),
        "cartridge_built": False,
        "emulator_verified": False,
        "hardware_verified": False,
        "release_approved": False,
        "distribution_licensed": False,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    digest = sha256((asm + "\0" + _LINKER + "\0" + _MAKEFILE + "\0" + manifest_json).encode()).hexdigest()
    return NativeNESSourceProject(asm, _LINKER, _MAKEFILE, manifest_json, digest)


def export_native_nes(
    project: NativeNESSourceProject, output: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("NES native source export requires authorization")
    if not isinstance(project, NativeNESSourceProject):
        raise NativeNESError("typed NES game source project required")
    folder = Path(output)
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(str(folder))
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("main.s", project.asm), ("nes.cfg", project.linker_cfg),
        ("Makefile", project.makefile), ("manifest.json", project.manifest_json),
    ):
        with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    return folder
