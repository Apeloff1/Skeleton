"""Core-neutral libretro time control and immutable RGB asset inspection.

Only the host drives libretro retro_run: pause does not call it, slow advances
exactly one frame and fast batches individually receipted native steps.
Wall-clock playback rates are UI scheduling targets, not measured guarantees.
"""
from __future__ import annotations

import hashlib
from typing import Any

INSPECTION_GRID = 16
MAX_INSPECTION_PIXELS = 4096 * 4096
TIMING_FACTORS = {
    "paused": (0,),
    "slow": (2, 4, 8),
    "normal": (1,),
    "fast": (2, 4, 8),
}


def normalize_timing(mode: object, factor: object) -> tuple[str, int]:
    if type(mode) is not str or mode not in TIMING_FACTORS:
        raise ValueError("Native speed mode must be paused, slow, normal or fast")
    if type(factor) is not int or factor not in TIMING_FACTORS[mode]:
        raise ValueError("Native speed factor outside the strictly bounded execution policy")
    return mode, factor


def native_execution_budget(mode: str, factor: int, base_frames: int) -> tuple[int, int]:
    """Return real libretro frames per step and steps per automatic burst."""
    normalize_timing(mode, factor)
    if type(base_frames) is not int or not 1 <= base_frames <= 60:
        raise ValueError("Approved native step frame count is invalid")
    if mode == "paused":
        return 0, 0
    if mode == "slow":
        return 1, 1
    if mode == "normal":
        return base_frames, 1
    return base_frames, factor


def inspect_rgb_frame(
    pixels: bytes, width: int, height: int, pixel_sha: str,
    audio_sha: str, native_run_cursor: int,
) -> dict[str, Any]:
    """Snapshot the real current RGB24 pixels: full-fidelity hashes, 16x16 tiles.

    Each tile's SHA covers ALL RGB bytes in the tile. Color/luma statistics
    explicitly sample at most 64 locations/tile for predictable CPU costs.
    Does not read game RAM, does not advance emulation, and contains no ROM.
    """
    if (
        type(pixels) is not bytes or type(width) is not int or type(height) is not int
        or not 1 <= width <= 4096 or not 1 <= height <= 4096
        or width * height > MAX_INSPECTION_PIXELS
        or len(pixels) != width * height * 3
        or type(pixel_sha) is not str or hashlib.sha256(pixels).hexdigest() != pixel_sha
        or type(audio_sha) is not str or len(audio_sha) != 64
        or type(native_run_cursor) is not int or native_run_cursor < 0
    ):
        raise ValueError("Native inspection source geometry or frame checksum differs")
    tiles: list[dict[str, Any]] = []
    count_x, count_y = min(width, INSPECTION_GRID), min(height, INSPECTION_GRID)
    for iy in range(count_y):
        y0, y1 = iy * height // count_y, (iy + 1) * height // count_y
        for ix in range(count_x):
            x0, x1 = ix * width // count_x, (ix + 1) * width // count_x
            full = hashlib.sha256()
            for y in range(y0, y1):
                offset = (y * width + x0) * 3
                full.update(pixels[offset:offset + (x1 - x0) * 3])
            # Evenly spaced, fixed-cost samples. The pixel checksum and tile
            # digest remain exact regardless of the sample approximation.
            xs = [x0 + (i * (x1 - x0 - 1)) // 7 for i in range(8)]
            ys = [y0 + (i * (y1 - y0 - 1)) // 7 for i in range(8)]
            channel_sum = [0, 0, 0]
            luminance_min, luminance_max = 255, 0
            dark = bright = 0
            for y in ys:
                for x in xs:
                    offset = (y * width + x) * 3
                    r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
                    channel_sum[0] += r
                    channel_sum[1] += g
                    channel_sum[2] += b
                    luma = (54 * r + 183 * g + 19 * b) // 256
                    luminance_min = min(luminance_min, luma)
                    luminance_max = max(luminance_max, luma)
                    dark += luma < 32
                    bright += luma > 223
            tiles.append({
                "x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0,
                "tile_rgb_sha256": full.hexdigest(),
                "sampled_rgb_mean": [round(value / 64, 2) for value in channel_sum],
                "sampled_luminance_range": [luminance_min, luminance_max],
                "sampled_dark_count": dark, "sampled_bright_count": bright,
                "samples": 64,
            })
    return {
        "schema_version": "skeleton.game.native_frame_inspection.v1",
        "pixel_sha256": pixel_sha,
        "audio_sha256": audio_sha,
        "native_run_cursor": native_run_cursor,
        "width": width, "height": height,
        "grid_columns": count_x, "grid_rows": count_y,
        "tiles": tiles, "total_tiles": len(tiles),
        "full_resolution_tile_hashes": True,
        "tile_color_statistics_are_sampled": True,
        "native_frames_executed_for_inspection": 0,
        "model_weights_updated": False,
    }
