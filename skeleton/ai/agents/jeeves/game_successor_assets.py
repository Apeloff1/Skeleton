"""Original deterministic sprite art shared by all successor renderers.

Every pixel is authored here from the new game's palette and seed. No source
images, cartridge bytes, image crops, third-party sprites or external resources
are read. Native RGB565 uses the explicit magenta transparency convention.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import struct
import zlib
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

ATLAS_SIZE = 128
CELL_SIZE = 16
ART_SCHEMA = "skeleton.game.original_successor_art.v1"
SLOTS = {
    "grass": 0,
    "water": 4,
    "sand": 8,
    "path": 9,
    "wall": 10,
    "soil": 11,
    "wet_soil": 12,
    "highland_grass": 13,
    "cave_floor": 14,
    "flowers": 15,
    "player_down": 16,
    "player_up": 17,
    "player_left": 18,
    "player_right": 19,
    "npc": 20,
    "guardian": 24,
    "boss": 27,
    "tree": 28,
    "bush": 29,
    "rock": 30,
    "fence": 31,
    "crop_seed": 32,
    "crop_sprout": 33,
    "crop_growing": 34,
    "crop_ripe": 35,
    "fish": 36,
    "rod_icon": 37,
    "watering_icon": 38,
    "hoe_icon": 39,
    "house_wall": 40,
    "roof": 41,
    "window": 42,
    "door": 43,
    "waystone": 44,
    "key": 45,
    "relic": 46,
    "pier": 47,
    "crops": 48,
    "quest": 56,
    "health": 57,
    "coin": 58,
    "seed": 59,
    "sword": 60,
    "rod": 61,
    "watering": 62,
    "compass": 63,
}


def _color(value: Any) -> tuple[int, int, int, int]:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or not value.startswith("#")
        or any(c not in "0123456789abcdefABCDEF" for c in value[1:])
    ):
        raise ValueError("original art requires exact six-digit color swatches")
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)) + (255,)


def _shade(color: tuple[int, ...], amount: float) -> tuple[int, int, int, int]:
    return tuple(max(0, min(255, round(c * amount))) for c in color[:3]) + (255,)


def _mix(a: tuple[int, ...], b: tuple[int, ...], fraction: float) -> tuple[int, int, int, int]:
    return tuple(round(a[i] * (1 - fraction) + b[i] * fraction) for i in range(3)) + (255,)


@lru_cache(maxsize=16)
def _pixels(palette: tuple[str, ...], seed: int) -> bytes:
    background, terrain, player, enemy, accent, collectible = map(_color, palette)
    shadow = _shade(background, 0.65)
    highlight = _mix(collectible, (255, 245, 220, 255), 0.4)
    soil = _mix(terrain, (111, 69, 48, 255), 0.72)
    water = _mix(accent, (39, 100, 147, 255), 0.62)
    wood = _mix(enemy, (128, 87, 53, 255), 0.65)
    skin = (223, 167, 123, 255)
    white = (239, 236, 213, 255)
    image = bytearray(ATLAS_SIZE * ATLAS_SIZE * 4)

    def pixel(slot: int, x: int, y: int, color: tuple[int, ...]) -> None:
        if not 0 <= x < 16 or not 0 <= y < 16:
            return
        offset = (((slot // 8) * 16 + y) * 128 + (slot % 8) * 16 + x) * 4
        image[offset : offset + 4] = bytes(color)

    def box(slot: int, x: int, y: int, w: int, h: int, color: tuple[int, ...]) -> None:
        for py in range(max(0, y), min(16, y + h)):
            for px in range(max(0, x), min(16, x + w)):
                pixel(slot, px, py, color)

    def ellipse(slot: int, x: int, y: int, rx: float, ry: float, color: tuple[int, ...]) -> None:
        for py in range(max(0, int(y - ry)), min(16, int(y + ry) + 1)):
            for px in range(max(0, int(x - rx)), min(16, int(x + rx) + 1)):
                if ((px - x) / rx) ** 2 + ((py - y) / ry) ** 2 <= 1:
                    pixel(slot, px, py, color)

    def line(slot: int, x: int, y: int, ex: int, ey: int, color: tuple[int, ...]) -> None:
        steps = max(abs(ex - x), abs(ey - y), 1)
        for step in range(steps + 1):
            pixel(slot, round(x + (ex - x) * step / steps), round(y + (ey - y) * step / steps), color)

    # Ground swatches are opaque and tile seamlessly. Dots and wave phases are
    # deterministic, newly authored texture rather than a copied tile sheet.
    for slot in range(16):
        rng = random.Random(seed ^ (slot + 1) * 0x45D9F3B)
        if slot < 4:
            base = _shade(terrain, 0.88 + slot * 0.035)
        elif slot < 8:
            base = water
        elif slot == 8:
            base = _mix(soil, highlight, 0.64)
        elif slot == 9:
            base = _mix(soil, highlight, 0.35)
        elif slot == 10:
            base = _mix(background, white, 0.22)
        elif slot in (11, 12):
            base = _shade(soil, 0.65 if slot == 12 else 0.95)
        elif slot == 13:
            base = _mix(terrain, background, 0.25)
        elif slot == 14:
            base = _mix(background, soil, 0.5)
        else:
            base = terrain
        box(slot, 0, 0, 16, 16, base)
        for _ in range(26):
            x, y = rng.randrange(16), rng.randrange(16)
            pixel(slot, x, y, _shade(base, rng.choice((0.8, 1.13))))
        if 4 <= slot < 8:
            for row in (4, 11):
                for x in range(16):
                    if (x + slot * 2) % 9 < 4:
                        pixel(slot, x, row + (x // 6) % 2, _mix(water, white, 0.28))
        elif slot == 10:
            for y in (0, 7, 15):
                box(slot, 0, y, 16, 1, shadow)
            line(slot, 7, 0, 7, 7, shadow)
            line(slot, 3, 8, 3, 14, shadow)
            line(slot, 12, 8, 12, 14, shadow)
        elif slot in (11, 12):
            for y in (3, 8, 13):
                box(slot, 0, y, 16, 1, _shade(soil, 0.5))
        elif slot == 15:
            for x, y in ((3, 4), (11, 6), (7, 12)):
                pixel(slot, x, y, highlight)
                pixel(slot, x - 1, y, collectible)
                pixel(slot, x + 1, y, collectible)
                pixel(slot, x, y + 1, accent)

    # The traveler has an original round cap, copper coat and a small satchel.
    # Directional poses share exact proportions, while facial/pack cues change.
    for slot in range(16, 24):
        facing = slot - 16 if slot < 20 else 0
        coat = player if slot < 20 else _mix((terrain, accent, enemy, collectible)[slot - 20], white, 0.12)
        ellipse(slot, 8, 14, 5, 1, shadow)
        box(slot, 5, 6, 7, 6, _shade(coat, 0.65))
        box(slot, 6, 6, 5, 5, coat)
        box(slot, 5, 12, 2, 3, wood)
        box(slot, 10, 12, 2, 3, wood)
        ellipse(slot, 8, 4, 3, 3, skin)
        box(slot, 5, 1, 7, 2, _shade(accent, 0.65))
        box(slot, 6, 0, 5, 2, accent)
        box(slot, 4, 3, 9, 1, _shade(accent, 0.8))
        box(slot, 4, 7, 2, 3, skin)
        box(slot, 12, 7, 2, 3, skin)
        if facing == 1:
            box(slot, 6, 7, 5, 4, wood)
            pixel(slot, 8, 8, highlight)
        elif facing == 2:
            pixel(slot, 5, 4, shadow)
            box(slot, 10, 7, 2, 4, wood)
        elif facing == 3:
            pixel(slot, 11, 4, shadow)
            box(slot, 4, 7, 2, 4, wood)
        else:
            pixel(slot, 6, 4, shadow)
            pixel(slot, 10, 4, shadow)
            pixel(slot, 8, 6, _shade(skin, 0.7))
            box(slot, 10, 8, 2, 3, wood)

    for slot in range(24, 28):
        color = _mix(enemy, terrain, (slot - 24) * 0.12)
        ellipse(slot, 8, 10, 6, 5, _shade(color, 0.6))
        ellipse(slot, 8, 8, 6, 5, color)
        box(slot, 3, 12, 3, 3, wood)
        box(slot, 10, 12, 3, 3, wood)
        line(slot, 3, 3, 1, 0, wood)
        line(slot, 12, 3, 14, 0, wood)
        pixel(slot, 5, 7, highlight)
        pixel(slot, 10, 7, highlight)
        if slot == 27:
            box(slot, 5, 1, 6, 2, collectible)
            for x in (5, 8, 10):
                pixel(slot, x, 0, highlight)

    box(28, 7, 7, 3, 9, wood)
    ellipse(28, 8, 6, 7, 6, _shade(terrain, 0.62))
    ellipse(28, 6, 4, 5, 4, terrain)
    ellipse(28, 10, 6, 5, 4, _shade(terrain, 0.86))
    line(28, 7, 10, 4, 8, wood)
    ellipse(29, 8, 11, 7, 4, _shade(terrain, 0.63))
    for x in (4, 8, 12):
        ellipse(29, x, 9, 3, 3, terrain)
    ellipse(30, 8, 11, 7, 4, _mix(background, white, 0.33))
    ellipse(30, 6, 8, 5, 4, _mix(background, white, 0.45))
    line(30, 4, 8, 8, 6, white)
    box(31, 2, 2, 2, 14, wood)
    box(31, 12, 2, 2, 14, wood)
    box(31, 0, 5, 16, 2, _shade(wood, 1.2))
    box(31, 0, 11, 16, 2, _shade(wood, 1.2))

    for slot in range(32, 36):
        ellipse(slot, 8, 13, 5, 2, soil)
        box(slot, 7, 9 - (slot - 32) * 2, 2, 5 + (slot - 32) * 2, terrain)
        if slot > 32:
            ellipse(slot, 5, 9, 3, 1, _shade(terrain, 1.25))
            ellipse(slot, 10, 7, 3, 1, _shade(terrain, 1.15))
        if slot == 35:
            ellipse(slot, 8, 6, 3, 3, collectible)
            pixel(slot, 7, 4, highlight)
    ellipse(36, 8, 8, 5, 3, accent)
    for x in range(3):
        box(36, 1 + x, 6 + x, 1, 5 - 2 * x, accent)
    pixel(36, 11, 7, white)
    pixel(36, 12, 7, shadow)
    line(37, 4, 14, 11, 1, wood)
    line(37, 11, 1, 14, 8, white)
    line(37, 14, 8, 11, 10, white)
    box(38, 4, 6, 7, 7, accent)
    line(38, 5, 6, 5, 2, shadow)
    line(38, 5, 2, 10, 2, shadow)
    line(38, 10, 2, 10, 6, shadow)
    line(38, 11, 7, 14, 4, accent)
    box(39, 7, 2, 2, 13, wood)
    box(39, 3, 1, 10, 3, _mix(background, white, 0.5))

    box(40, 0, 0, 16, 16, _mix(soil, white, 0.28))
    for y in (3, 8, 13):
        line(40, 0, y, 15, y, soil)
    for y in range(16):
        box(41, 0, y, 16, 1, _shade(enemy, 0.7 + (y % 4) * 0.09))
    box(42, 1, 1, 14, 14, wood)
    box(42, 3, 3, 10, 10, _mix(water, white, 0.4))
    box(42, 7, 2, 2, 12, wood)
    box(42, 2, 7, 12, 2, wood)
    box(43, 2, 1, 12, 15, _shade(wood, 0.7))
    box(43, 4, 2, 8, 14, wood)
    pixel(43, 10, 9, highlight)
    ellipse(44, 8, 14, 6, 2, shadow)
    box(44, 4, 3, 8, 11, _mix(background, white, 0.38))
    box(44, 6, 1, 4, 3, _mix(accent, white, 0.45))
    line(44, 8, 5, 8, 11, accent)
    line(44, 6, 8, 10, 8, accent)
    ellipse(45, 5, 5, 3, 3, collectible)
    ellipse(45, 5, 5, 1, 1, shadow)
    line(45, 7, 7, 13, 13, collectible)
    box(45, 11, 11, 3, 2, collectible)
    for y in range(3, 13):
        width = 1 + min(y - 3, 12 - y)
        box(46, 8 - width, y, width * 2 + 1, 1, accent)
    line(46, 8, 3, 5, 8, highlight)
    box(47, 0, 0, 16, 16, wood)
    for y in (3, 7, 11, 15):
        line(47, 0, y, 15, y, _shade(wood, 0.6))
    for x in (2, 13):
        for y in (2, 6, 10, 14):
            pixel(47, x, y, shadow)

    for slot in range(48, 56):
        color = _mix((collectible, accent, enemy, player)[(slot - 48) % 4], white, 0.1 * (slot % 3))
        ellipse(slot, 8, 10, 4 + (slot % 2), 4, color)
        box(slot, 7, 3, 2, 4, terrain)
        ellipse(slot, 5, 4, 3, 1, terrain)
        pixel(slot, 6, 8, highlight)
    box(56, 3, 2, 10, 12, highlight)
    for y in (5, 8, 11):
        line(56, 5, y, 10, y, wood)
    ellipse(57, 5, 6, 3, 3, enemy)
    ellipse(57, 10, 6, 3, 3, enemy)
    for y in range(7, 13):
        width = 12 - y
        box(57, 8 - width, y, width * 2, 1, enemy)
    ellipse(58, 8, 8, 6, 6, _shade(collectible, 0.7))
    ellipse(58, 8, 7, 5, 5, collectible)
    line(58, 8, 4, 8, 10, highlight)
    ellipse(59, 6, 9, 3, 4, wood)
    ellipse(59, 10, 7, 3, 4, collectible)
    line(60, 4, 12, 12, 2, white)
    line(60, 5, 12, 13, 2, accent)
    line(60, 2, 11, 7, 14, collectible)
    line(60, 4, 13, 2, 15, wood)
    line(61, 4, 14, 11, 1, wood)
    line(61, 11, 1, 14, 8, white)
    line(61, 14, 8, 11, 10, white)
    box(62, 4, 6, 7, 7, accent)
    line(62, 4, 6, 4, 2, wood)
    line(62, 4, 2, 10, 2, wood)
    line(62, 10, 2, 10, 6, wood)
    line(62, 11, 7, 14, 4, accent)
    ellipse(63, 8, 8, 6, 6, wood)
    ellipse(63, 8, 8, 5, 5, white)
    line(63, 8, 3, 5, 11, enemy)
    line(63, 8, 3, 10, 11, accent)
    return bytes(image)


def _png(rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + rgba[row * 512 : (row + 1) * 512] for row in range(128))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!IIBBBBB", 128, 128, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def successor_art(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Actual original 128x128 RGBA/PNG and matching RGB565 atlas data."""
    palette = spec.get("palette")
    keys = ("background", "terrain", "player", "enemy", "accent", "collectible")
    if not isinstance(palette, Mapping) or set(palette) != set(keys):
        raise ValueError("original atlas requires the complete authored palette")
    colors = tuple(palette[key] for key in keys)
    for color in colors:
        _color(color)
    seed = spec.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise ValueError("original atlas seed exceeds bounds")
    rgba = _pixels(colors, seed)
    png = _png(rgba)
    rgb565 = []
    for offset in range(0, len(rgba), 4):
        r, g, b, a = rgba[offset : offset + 4]
        packed = 0xF81F if a == 0 else ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        if a and packed == 0xF81F:
            packed = 0xF81E
        rgb565.append(packed)
    return {
        "png_base64": base64.b64encode(png).decode("ascii"),
        "rgb565": rgb565,
        "rgba": rgba,
        "digest": hashlib.sha256(png).hexdigest(),
    }


def emit_successor_assets(spec: Mapping[str, Any]) -> dict[str, str]:
    """Emit source-safe asset metadata and the exact native pixel header."""
    art = successor_art(spec)
    manifest = {
        "schema_version": ART_SCHEMA,
        "width": 128,
        "height": 128,
        "cell_size": 16,
        "slots": SLOTS,
        "png_base64": art["png_base64"],
        "art_digest": art["digest"],
        "origin": "entirely original procedural pixel art; no source game images",
    }
    values = art["rgb565"]
    rows = [
        ",".join(f"0x{value:04x}" for value in values[index : index + 16])
        for index in range(0, len(values), 16)
    ]
    header = "\n".join(
        [
            "/* Original generated atlas; RGB565 magenta is transparent. */",
            "#ifndef SUCCESSOR_ART_H",
            "#define SUCCESSOR_ART_H",
            "#include <stdint.h>",
            "#define SUCCESSOR_ART_WIDTH 128",
            "#define SUCCESSOR_ART_HEIGHT 128",
            "#define SUCCESSOR_ART_CELL 16",
            "static const uint16_t SUCCESSOR_ART_PIXELS[16384] = {",
            ",\n".join(rows),
            "};",
            "#endif",
            "",
        ]
    )
    return {
        "game/successor/art.json": json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        "game/generated/native/pc_linux/game_art.h": header,
    }
