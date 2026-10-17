"""Dragon's actual bounded RGB24 optical companion for native emulator episodes.

Reuses the canonical host frame inspector: pixels are verified and inspected
in the isolated emulator host; ROM bytes, screenshots and raw audio are NOT
copied to the long-term dataset. Optical measurement is not semantic VLM
vision and cannot infer stories, object names or game completion.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .game_learning import _digest

SCHEMA = "skeleton.game.dragon_native_optical_observation.v1"


class DragonOpticalError(ValueError):
    pass


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise DragonOpticalError(why)


def observe_native_frame(environment: Any, *, expected_frame_sha256: str) -> dict[str, Any]:
    """Read actual current RGB through inspect_frame; never advance gameplay."""
    inspect = getattr(environment, "inspect_frame", None)
    _require(callable(inspect), "Dragon optical observation requires native pixel inspection")
    frame = inspect()
    _require(isinstance(frame, Mapping)
             and frame.get("schema_version") == "skeleton.game.native_frame_inspection.v1"
             and frame.get("pixel_sha256") == expected_frame_sha256
             and frame.get("full_resolution_tile_hashes") is True
             and frame.get("tile_color_statistics_are_sampled") is True
             and frame.get("native_frames_executed_for_inspection") == 0,
             "source pixel inspection is not tied to the executed emulator frame")
    width, height = frame.get("width"), frame.get("height")
    tiles = frame.get("tiles")
    _require(type(width) is int and type(height) is int
             and 1 <= width <= 4096 and 1 <= height <= 4096
             and width * height <= 4096 * 4096
             and type(tiles) is list and 1 <= len(tiles) <= 256
             and frame.get("total_tiles") == len(tiles),
             "Dragon native optical geometry exceeds bounds")
    dark = bright = total = 0
    rgb_sum = [0.0, 0.0, 0.0]
    luma_min, luma_max = 255, 0
    tile_ids: list[str] = []
    for tile in tiles:
        _require(type(tile) is dict and tile.get("samples") == 64
                 and type(tile.get("sampled_rgb_mean")) is list
                 and len(tile["sampled_rgb_mean"]) == 3
                 and all(type(x) in (int, float) and 0 <= x <= 255
                         for x in tile["sampled_rgb_mean"])
                 and type(tile.get("sampled_luminance_range")) is list
                 and len(tile["sampled_luminance_range"]) == 2
                 and all(type(x) is int and 0 <= x <= 255
                         for x in tile["sampled_luminance_range"])
                 and tile["sampled_luminance_range"][0] <= tile["sampled_luminance_range"][1]
                 and type(tile.get("sampled_dark_count")) is int
                 and type(tile.get("sampled_bright_count")) is int
                 and 0 <= tile["sampled_dark_count"] <= 64
                 and 0 <= tile["sampled_bright_count"] <= 64,
                 "RGB tile sample statistics are malformed")
        digest = tile.get("tile_rgb_sha256")
        _require(type(digest) is str and len(digest) == 64
                 and all(ch in "0123456789abcdef" for ch in digest),
                 "RGB tile must have exact native SHA-256 provenance")
        tile_ids.append(digest)
        for channel in range(3):
            rgb_sum[channel] += tile["sampled_rgb_mean"][channel]
        dark += tile["sampled_dark_count"]
        bright += tile["sampled_bright_count"]
        total += 64
        luma_min = min(luma_min, tile["sampled_luminance_range"][0])
        luma_max = max(luma_max, tile["sampled_luminance_range"][1])
    _require(dark + bright <= total, "optical color bins overlap incorrectly")
    result = {
        "schema_version": SCHEMA,
        "source": "actual_native_rgb24_pixel_tiles",
        "frame_pixel_sha256": expected_frame_sha256,
        "tile_sequence_sha256": _digest(tile_ids),
        "tile_count": len(tile_ids),
        "sampled_rgb_mean": [round(x / len(tiles), 3) for x in rgb_sum],
        "sampled_luminance_range": [luma_min, luma_max],
        "sampled_dark_fraction": round(dark / total, 6),
        "sampled_bright_fraction": round(bright / total, 6),
        "unique_rgb_tile_patterns": len(set(tile_ids)),
        "pixels_checked_by_existing_native_inspector": width * height,
        "new_native_steps_for_observation": 0,
        "semantic_entities_inferred": False,
        "independent_model_witness_executed": False,
        "weights_updated": 0,
    }
    result["observation_digest"] = _digest(result)
    return result


def verify_native_observation(value: Any, *, frame_sha256: str) -> None:
    """Validate source association and inner digest before Dragon indexes it."""
    _require(type(value) is dict and value.get("schema_version") == SCHEMA
             and value.get("source") == "actual_native_rgb24_pixel_tiles"
             and value.get("frame_pixel_sha256") == frame_sha256
             and value.get("new_native_steps_for_observation") == 0
             and value.get("semantic_entities_inferred") is False
             and value.get("independent_model_witness_executed") is False
             and value.get("weights_updated") == 0
             and type(value.get("tile_count")) is int and 1 <= value["tile_count"] <= 256
             and type(value.get("unique_rgb_tile_patterns")) is int
             and 1 <= value["unique_rgb_tile_patterns"] <= value["tile_count"]
             and value.get("observation_digest") == _digest({
                 k: x for k, x in value.items() if k != "observation_digest"
             }), "Dragon optical witness identity does not match native frame")
