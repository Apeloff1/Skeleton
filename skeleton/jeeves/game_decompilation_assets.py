"""Finite pixel-accurate decode and evidence for known console graphic layouts.

NES CHR ROM is structurally identified by iNES. Other cartridge contents are
NOT assumed to be sprites; explicit offset candidates are labeled unverified.
No original assets or raw cartridge bytes enter production training outputs.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Any

from .game_console_assets import TileCodec, decode_tiles, png_rgba
from .game_learning_ingestion import _rom_nes

MAX_TILE_BYTES = 32768
MAX_TILES_PER_ATLAS = 1024
MAX_ATLAS_BYTES = 2 * 1024 * 1024
PALETTE = ((0, 0, 0, 255), (85, 85, 85, 255),
           (170, 170, 170, 255), (255, 255, 255, 255))


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _tile_statistics(tiles: tuple[tuple[int, ...], ...]) -> dict[str, Any]:
    patterns = Counter(_sha(bytes(tile)) for tile in tiles)
    occupancy = Counter()
    edge_total = 0
    for tile in tiles:
        occupancy.update(tile)
        for y in range(8):
            for x in range(8):
                pos = y * 8 + x
                edge_total += x < 7 and tile[pos] != tile[pos + 1]
                edge_total += y < 7 and tile[pos] != tile[pos + 8]
    n = len(tiles)
    return {
        "tiles": n,
        "unique_tile_sha256": len(patterns),
        "exact_duplicate_tile_count": n - len(patterns),
        "palette_index_pixel_counts": [
            {"index": index, "pixels": count}
            for index, count in sorted(occupancy.items())
        ],
        "edge_change_count": edge_total,
        "edge_density_over_possible_neighbors": round(edge_total / (n * 112), 6) if n else 0,
        "tile_density_interpretation": "structural indices, not classified sprite objects",
        "frame_assembly_or_animation_inferred": False,
    }


def _atlas_rgba(tiles: tuple[tuple[int, ...], ...], *, cols: int = 16) -> tuple[int, int, bytes]:
    if not tiles or len(tiles) > MAX_TILES_PER_ATLAS:
        raise ValueError("Tile atlas count outside bounded region")
    if cols != 16:
        raise ValueError("Only 16-column deterministic sprite atlases supported")
    width, height = 8 * cols, 8 * math.ceil(len(tiles) / cols)
    output = bytearray(width * height * 4)
    for n, tile in enumerate(tiles):
        x0, y0 = (n % cols) * 8, (n // cols) * 8
        for y in range(8):
            for x in range(8):
                index = tile[y * 8 + x]
                color = PALETTE[index] if index < len(PALETTE) else (index, index, index, 255)
                start = ((y0 + y) * width + x0 + x) * 4
                output[start:start + 4] = bytes(color)
    return width, height, bytes(output)


def decode_tile_region(
    data: bytes, *, offset: int, length: int, codec: str,
    provenance: str, allow_png_export: bool = False,
) -> tuple[dict[str, Any], bytes | None]:
    """Decode only exact explicitly delimited tile bytes; do not search arbitrary ROM."""
    if (type(data) is not bytes or type(offset) is not int or type(length) is not int
        or not 0 <= offset < len(data) or not 1 <= length <= MAX_TILE_BYTES
        or offset + length > len(data) or type(provenance) is not str
        or not 1 <= len(provenance) <= 128
        or type(allow_png_export) is not bool):
        raise ValueError("Invalid bounded tile region, preview authority or source declaration")
    if codec not in {"nes_2bpp", "gb_2bpp", "snes_4bpp", "genesis_4bpp",
                     "gba_4bpp", "gba_8bpp", "sms_4bpp"}:
        raise ValueError("Unsupported tile layout; no speculative codec fallback")
    size = 8 * (2 if codec in {"nes_2bpp", "gb_2bpp"} else 8 if codec == "gba_8bpp" else 4)
    if length % size:
        raise ValueError("Tile range must contain a whole number of native tiles")
    region = data[offset:offset + length]
    tiles = decode_tiles(region, TileCodec(codec))
    groups = []
    previews = bytearray()
    for begin in range(0, len(tiles), MAX_TILES_PER_ATLAS):
        block = tiles[begin:begin + MAX_TILES_PER_ATLAS]
        w, h, rgba = _atlas_rgba(block)
        png = png_rgba(rgba, w, h)
        groups.append({
            "tile_start": begin, "tile_count": len(block),
            "preview_width": w, "preview_height": h,
            "rgba_pixel_sha256": _sha(rgba), "preview_png_sha256": _sha(png),
        })
        if allow_png_export:
            # Multiple blocks cannot be serialized as one ambiguous PNG;
            # callers must explicitly split regions at the 1024-tile bound.
            if len(groups) > 1:
                raise ValueError("PNG export requires <=1024 exactly delimited tiles")
            previews.extend(png)
    return {
        "schema_version": "skeleton.game.decompiled_tile_region.v1",
        "source_region_sha256": _sha(region),
        "byte_offset": offset,
        "byte_length": length,
        "codec": codec, "provenance": provenance,
        "palette": "synthetic_grayscale_preview_not_original_hardware_palette",
        "layout_status": (
            "confirmed_format_region" if provenance == "ines_chr_rom"
            else "operator_declared_tile_candidate_not_verified_as_graphics"
        ),
        "statistics": _tile_statistics(tiles),
        "atlas_groups": groups,
        "raw_tile_bytes_exported": False,
        "full_resolution_png_exported": bool(allow_png_export),
        "sprite_identity_or_game_object_inferred": False,
    }, bytes(previews) if allow_png_export else None


def extract_nes_chr(
    data: bytes, *, preview_authorized: bool = False,
) -> tuple[dict[str, Any], tuple[tuple[str, bytes], ...]]:
    """Exact iNES character-ROM tile region, with one 8 KiB preview per CHR bank."""
    metadata = _rom_nes(data)
    layout = [row for row in metadata["layout"] if row["kind"] == "character_rom"]
    if not layout:
        return {
            "schema_version": "skeleton.game.nes_chr_extraction.v1",
            "chr_present": False, "regions": [], "total_tiles": 0,
            "chr_ram_cannot_be_recovered_from_static_rom": True,
        }, ()
    chr_row = layout[0]
    offset, count = chr_row["offset"], chr_row["byte_length"]
    if count > 2 * 1024 * 1024:
        raise ValueError("CHR collection exceeds bounded static-source budget")
    regions = []
    files = []
    for index, start in enumerate(range(0, count, 8192)):
        size = min(8192, count - start)
        region, image = decode_tile_region(
            data, offset=offset + start, length=size,
            codec="nes_2bpp", provenance="ines_chr_rom",
            allow_png_export=preview_authorized,
        )
        region["chr_bank"] = index
        regions.append(region)
        if image is not None:
            if len(image) > MAX_ATLAS_BYTES:
                raise ValueError("Decoded preview unexpectedly exceeds cap")
            files.append(("nes_chr_bank_" + str(index).zfill(3) + ".png", image))
    return {
        "schema_version": "skeleton.game.nes_chr_extraction.v1",
        "chr_present": True, "chr_rom_sha256": _sha(data[offset:offset + count]),
        "regions": regions, "total_tiles": count // 16,
        "chr_bank_count": len(regions),
        "true_graphic_elements_not_guaranteed": True,
        "unlicensed_copying_is_not_approved": True,
    }, tuple(files)
