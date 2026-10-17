"""Attest actual GB/GBC ROM pixels against the six original studio tiles.

Use RGBLINK-produced bank-0 Tiles/TilesEnd labels; never search for matching
bytes or assume a ROM offset. A valid Nintendo cartridge header alone is
insufficient proof that the compiled game retained authored art.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

from .contracts import canonical_digest
from .studio_build_qualification import _header, _regular

SCHEMA = "skeleton.game_builder.game_boy_compiled_sprite_parity.v1"
_REQUIRED = frozenset(("Tiles", "TilesEnd"))


class GameBoyROMArtError(ValueError):
    """Compiled handheld cartridge does not contain original studio tiles."""


def parse_game_boy_tile_labels(raw: bytes) -> tuple[int, int]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 128_000:
        raise GameBoyROMArtError("bounded RGBLINK linker symbols required")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise GameBoyROMArtError("RGBLINK symbols must be ASCII") from exc
    found: dict[str, int] = {}
    for line in text.splitlines():
        result = re.fullmatch(
            r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+(Tiles|TilesEnd)",
            line.strip(),
        )
        if result is None:
            continue
        bank, offset, label = int(result[1], 16), int(result[2], 16), result[3]
        if label in found or bank != 0 or not 0x0150 <= offset <= 0x3FFF:
            raise GameBoyROMArtError("original tile label duplicated or outside ROM0")
        found[label] = offset
    if set(found) != _REQUIRED:
        raise GameBoyROMArtError("actual ROM0 sprite tile symbols unavailable")
    start, end = found["Tiles"], found["TilesEnd"]
    if end - start != 96:
        raise GameBoyROMArtError("linked original tile inventory is not six 2bpp tiles")
    return start, end


def _animation_tile_bounds(symbols: bytes) -> tuple[int, int]:
    try:
        text = symbols.decode("ascii")
    except UnicodeDecodeError as exc:
        raise GameBoyROMArtError("non-ASCII hero animation linker labels") from exc
    names = {}
    for line in text.splitlines():
        result = re.fullmatch(
            r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+(AnimationTiles|AnimationTilesEnd)",
            line.strip(),
        )
        if result is None:
            continue
        bank, offset, label = int(result[1], 16), int(result[2], 16), result[3]
        if label in names or bank != 0 or not 0x0150 <= offset <= 0x3FFF:
            raise GameBoyROMArtError("hero animation tile symbols outside ROM0")
        names[label] = offset
    if set(names) != {"AnimationTiles", "AnimationTilesEnd"}:
        raise GameBoyROMArtError("actual hero animation tile linker section missing")
    return names["AnimationTiles"], names["AnimationTilesEnd"]


def inspect_compiled_game_boy_art(
    rom: bytes, symbol_map: bytes, source_project: str | Path, *,
    color: bool = False,
) -> dict:
    if type(rom) is not bytes or type(color) is not bool:
        raise GameBoyROMArtError("typed GB/GBC ROM and color model required")
    try:
        _header("gbc" if color else "gb", rom)
        original = _regular(Path(source_project) / "assets/tiles/runtime.bin", 1024)
    except (OSError, ValueError) as exc:
        raise GameBoyROMArtError("authored handheld source assets unavailable") from exc
    if len(original) != 96:
        raise GameBoyROMArtError("GB/GBC original studio tile pack must be 96 bytes")
    first, last = parse_game_boy_tile_labels(symbol_map)
    if last > len(rom) or rom[first:last] != original:
        raise GameBoyROMArtError("compiled handheld ROM pixels differ from original art")
    animation = Path(source_project) / "assets/tiles/hero_animation.bin"
    animated_frames = 0
    animation_digest = None
    if animation.exists() or animation.is_symlink():
        try:
            packed = _regular(animation, 64)
        except (OSError, ValueError) as exc:
            raise GameBoyROMArtError("authored hero frames inaccessible") from exc
        if (not 16 <= len(packed) <= 64 or len(packed) % 16
                or packed[:16] != original[80:96]):
            raise GameBoyROMArtError("hero frame zero differs from original tile 5")
        frame_start, frame_end = _animation_tile_bounds(symbol_map)
        if (frame_start != last or frame_end != frame_start + len(packed) - 16
                or frame_end > len(rom)
                or rom[frame_start:frame_end] != packed[16:]):
            raise GameBoyROMArtError("compiled hero animation differs from authored frames")
        animated_frames = len(packed) // 16
        animation_digest = sha256(packed).hexdigest()
    body = {
        "schema": SCHEMA,
        "target": "nintendo_game_boy_color" if color else "nintendo_game_boy",
        "compiled_rom_sha256": sha256(rom).hexdigest(),
        "linker_symbol_sha256": sha256(symbol_map).hexdigest(),
        "source_tiles_sha256": sha256(original).hexdigest(),
        "compiled_tile_sha256": sha256(rom[first:last]).hexdigest(),
        "tile_rom0_offset": first,
        "tile_byte_count": len(original),
        "matched_indexed_pixels": 384 + max(0, animated_frames - 1) * 64,
        "original_animation_frame_count": animated_frames,
        "original_animation_sha256": animation_digest,
        "emulated_lcd_pixels_verified": False,
        "hardware_colors_verified": False,
        "release_authorized": False,
    }
    return {**body, "parity_digest": canonical_digest(body)}


__all__ = [
    "GameBoyROMArtError", "parse_game_boy_tile_labels",
    "inspect_compiled_game_boy_art",
]
