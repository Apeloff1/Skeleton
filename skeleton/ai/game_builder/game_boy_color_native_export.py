"""Actual RGBDS Game Boy Color ROM source, with distinct CGB hardware behavior.

This is a separate CGB-only cartridge, not a recolored DMG screenshot: it
writes RGB555 palettes using FF68/FF69 and FF6A/FF6B, switches VRAM bank using
FF4F, and installs per-original-tile color attributes for all authored stages.
The tested monochrome engine supplies baseline real gameplay and controllers.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .game_boy_native_export import GameBoySourceError, compile_native_game_boy
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

# Eight CGB BG palettes. Slots 0-4 distinguish floor, wall, gem, hazard, gate.
# All values are original designer RGB555 choices, not commercial game assets.
_BG = (
    (0x7FFF,0x56B5,0x294A,0x1042),
    (0x7FFF,0x6B5A,0x35CE,0x18C6),
    (0x7FFF,0x57FF,0x03FF,0x01AE),
    (0x7FFF,0x7EBC,0x7C10,0x3008),
    (0x7FFF,0x63FF,0x3DAA,0x1140),
    (0x7FFF,0x56B5,0x294A,0x1042),
    (0x7FFF,0x56B5,0x294A,0x1042),
    (0x7FFF,0x56B5,0x294A,0x1042),
)
_OBJ = (0x7FFF,0x7FE0,0x4DB7,0x3C14)
_ATTR = {".":0,"S":0,"#":1,"C":2,"H":3,"G":4}
_CGB = r"""
; GBC hardware registers, not present in original DMG.
DEF rVBK EQU $FF4F
DEF rBCPS EQU $FF68
DEF rBCPD EQU $FF69
DEF rOCPS EQU $FF6A
DEF rOCPD EQU $FF6B
"""
_ROUTINES = r"""
InitCGBPalettes:
    ld a, $80
    ldh [rBCPS], a
    ld hl, CGBBackgroundPalette
    ld b, 64
.bg:
    ld a, [hli]
    ldh [rBCPD], a
    dec b
    jr nz, .bg
    ld a, $80
    ldh [rOCPS], a
    ld hl, CGBSpritePalette
    ld b, 8
.obj:
    ld a, [hli]
    ldh [rOCPD], a
    dec b
    jr nz, .obj
    ret

; Only called when the LCD has already been disabled.
; Restoring VRAM bank 0 is mandatory before reading game tile collisions.
LoadCGBAttributes:
    ld a, 1
    ldh [rVBK], a
    ld a, [Level]
    add a
    ld e, a
    ld d, 0
    ld hl, CGBAttributePointers
    add hl, de
    ld a, [hli]
    ld e, a
    ld a, [hl]
    ld d, a
    ld hl, TILEMAP
    ld bc, BG_BYTE_COUNT
    call CopyBytes
    xor a
    ldh [rVBK], a
    ret
"""


class GameBoyColorSourceError(ValueError):
    """Invalid original color cartridge game, rights or source envelope."""


@dataclass(frozen=True, slots=True)
class GameBoyColorSourceProject:
    asm: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_cgb_rgbds_rgb555_attribute_rom_source"
    binary_compiled: bool = False
    cgb_emulator_verified: bool = False
    real_hardware_verified: bool = False


def _exact(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise GameBoyColorSourceError("CGB source insertion contract invalid")
    return source.replace(before, after)


def _palette_lines(palettes: tuple[tuple[int,...], ...]) -> str:
    return "\n".join(
        "    db " + ", ".join(
            "$" + format(c & 255, "02X") + ", $" + format(c >> 8, "02X")
            for c in palette
        ) for palette in palettes
    )


def compile_native_game_boy_color(
    world: PlayableWorld, rights: HomebrewSource, *, authorized: bool,
) -> GameBoyColorSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native CGB game needs explicit original-homebrew authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(rights, HomebrewSource):
        raise GameBoyColorSourceError("typed original game and clearance required")
    if world.intent.project_id != rights.project_id:
        raise GameBoyColorSourceError("CGB project identity and rights mismatch")
    try:
        dmgb = compile_native_game_boy(world, rights, authorized=True)
    except GameBoySourceError as exc:
        raise GameBoyColorSourceError("original world exceeds base CGB gameplay engine budget") from exc
    cgb_plan = compile_port(PortRequest((rights,), "nintendo_game_boy_color", PortMode.REVERSE_CONSTRAINED))
    code = dmgb.asm
    code = _exact(code, "DEF rJOYP EQU $FF00\n", _CGB + "DEF rJOYP EQU $FF00\n")
    code = _exact(code,
        "    ld [SPRITE_OAM_BASE+3], a\n    call LoadLevelWithoutWait",
        "    ld [SPRITE_OAM_BASE+3], a\n    call InitCGBPalettes\n    call LoadLevelWithoutWait")
    code = _exact(code,
        "    ld hl, TILEMAP\n    ld bc, BG_BYTE_COUNT\n    call CopyBytes\n    ret",
        "    ld hl, TILEMAP\n    ld bc, BG_BYTE_COUNT\n    call CopyBytes\n    call LoadCGBAttributes\n    ret")
    code = _exact(code, 'SECTION "Pixel Art", ROM0', _ROUTINES + '\nSECTION "Pixel Art", ROM0')
    maps = []
    for level in world.levels:
        rows = []
        for row in level.rows:
            numbers = [_ATTR[c] for c in row] + [0]*(32-len(row))
            rows.append("    db " + ", ".join("$" + format(n,"02X") for n in numbers))
        rows.extend("    ds 32, 0" for _ in range(18-len(level.rows)))
        maps.append("CGBAttributeMap" + str(level.index) + ":\n" + "\n".join(rows))
    attr_section = (
        'SECTION "Original CGB RGB555 Palette Artwork", ROM0\n'
        "CGBBackgroundPalette:\n" + _palette_lines(_BG) + "\n"
        "CGBSpritePalette:\n" + _palette_lines((_OBJ,)) + "\n"
        'SECTION "Original CGB Tile Color Attributes", ROM0\n'
        "CGBAttributePointers:\n"
        + "\n".join("    dw CGBAttributeMap" + str(i) for i in range(len(world.levels)))
        + "\n" + "\n\n".join(maps) + "\n\n"
    )
    code = _exact(code, 'SECTION "Game State", WRAM0', attr_section + 'SECTION "Game State", WRAM0')
    makefile = _exact(dmgb.makefile,
        "$(RGBFIX) -v -p 0 -t SKELORIG $@",
        "$(RGBFIX) -v -C -p 0 -t SKELCOLOR $@")
    if makefile.count("skeleton-original.gb") != 2:
        raise GameBoyColorSourceError("unrecognized source make target layout")
    makefile = makefile.replace("skeleton-original.gb", "skeleton-original.gbc")
    manifest = json.loads(dmgb.manifest_json)
    manifest.update({
        "schema": "skeleton.game_builder.native_cgb_source.v1",
        "platform": "nintendo_game_boy_color",
        "engine": "original_cgb_rgb555_color_attribute_maze.v1",
        "hardware_color_only_flag": 0xC0,
        "background_palettes": 8,
        "independent_original_tile_palettes": 5,
        "sprite_palettes": 1,
        "vram_bank1_tile_attributes": True,
        "cgb_blueprint_digest": cgb_plan.digest,
        "native_color_rom_compiled": False,
        "cgb_emulator_playthrough_verified": False,
        "physical_color_hardware_verified": False,
        "release_approved": False,
        "licensed_distribution": False,
    })
    manifest_json = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    digest = sha256((code+"\0"+makefile+"\0"+manifest_json).encode()).hexdigest()
    return GameBoyColorSourceProject(code, makefile, manifest_json, digest)


def export_native_game_boy_color(
    project: GameBoyColorSourceProject, output: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native Game Boy Color source export needs authorization")
    if not isinstance(project, GameBoyColorSourceProject):
        raise GameBoyColorSourceError("typed CGB game required")
    root = Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True, exist_ok=False)
    for name,data in (
        ("main.asm",project.asm),("Makefile",project.makefile),
        ("manifest.json",project.manifest_json),
    ):
        with (root/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(data)
    return root
