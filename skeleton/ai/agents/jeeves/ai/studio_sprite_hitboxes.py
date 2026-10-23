"""Pixel-exact, bounded authored sprite hitboxes for native game consumers.

Transforms reviewed alpha mask bits into deterministic non-overlapping
rectangles, merging identical runs across adjacent source rows. These are
EXACT mask geometry, not inferred approximate bounding boxes; every pixel
covered is proven to equal the author-defined alpha threshold occupancy.
The emitted JSON can support physics adapters, collision debug views and
state-specific SpriteFrames without granting game execution permission.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.sprite_collision_rectangles.v1"
MAX_SHAPES_PER_FRAME = 4096
MAX_TOTAL_SHAPES = 16384


class SpriteCollisionError(ValueError):
    """Sprite collision source cannot be reconstructed losslessly."""


def _bits(source: Any, *, width: int, height: int) -> list[list[bool]]:
    if (type(source) is not str
            or len(source) != 2 * ((width * height + 7) // 8)):
        raise SpriteCollisionError("original collision mask byte count differs")
    try:
        packed = bytes.fromhex(source)
    except ValueError as exc:
        raise SpriteCollisionError("original collision bits are invalid hexadecimal") from exc
    size = width * height
    if size % 8 and packed[-1] & ~((1 << (size % 8)) - 1):
        raise SpriteCollisionError("alpha mask has nonzero bits past source frame")
    return [
        [
            bool(packed[(y * width + x) >> 3] & (1 << ((y * width + x) & 7)))
            for x in range(width)
        ]
        for y in range(height)
    ]


def _runs(row: list[bool]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    x = 0
    while x < len(row):
        if not row[x]:
            x += 1
            continue
        beginning = x
        while x < len(row) and row[x]:
            x += 1
        spans.append((beginning, x))
    return spans


def compile_exact_sprite_hitboxes(sprite: Mapping[str, Any]) -> dict[str, Any]:
    """Generate pixel-exact source geometry backed by alpha bitmask receipts."""
    if not isinstance(sprite, Mapping):
        raise SpriteCollisionError("reviewed original sprite receipt required")
    data = dict(sprite)
    claimed = data.pop("receipt_sha256", None)
    if (type(claimed) is not str or claimed != digest(data)
            or sprite.get("schema_version") !=
            "skeleton.jeeves.authored_sprite_atlas.v1"):
        raise SpriteCollisionError("sprite hitbox input lacks verified source lineage")
    frames = sprite.get("frames")
    scale = sprite.get("pixel_scale")
    width_px = sprite.get("frame_width_px")
    height_px = sprite.get("frame_height_px")
    if (type(scale) is not int or not 1 <= scale <= 8
            or type(width_px) is not int or type(height_px) is not int
            or width_px <= 0 or height_px <= 0
            or width_px % scale or height_px % scale
            or not isinstance(frames, list) or not 1 <= len(frames) <= 64):
        raise SpriteCollisionError("sprite shape dimensions are unsupported")
    width, height = width_px // scale, height_px // scale
    if width > 64 or height > 64:
        raise SpriteCollisionError("pixel-perfect source exceeds sprite policy")
    result_frames: list[dict[str, Any]] = []
    total_shapes = 0
    for frame in frames:
        if not isinstance(frame, dict):
            raise SpriteCollisionError("collision frame is not reviewed source")
        mask_hex = frame.get("collision_mask_bits_hex")
        rows = _bits(mask_hex, width=width, height=height)
        packed = bytes.fromhex(mask_hex)
        if sha256(packed).hexdigest() != frame.get("collision_mask_sha256"):
            raise SpriteCollisionError("alpha bit mask SHA differs from source")
        coverage = sum(sum(row) for row in rows)
        if coverage != frame.get("opaque_source_pixels"):
            raise SpriteCollisionError("source occupancy contradicts collision alpha bits")
        active: dict[tuple[int, int], list[int]] = {}
        rectangles: list[list[int]] = []
        for y, row in enumerate(rows):
            present = set(_runs(row))
            for run in sorted(set(active) - present):
                rectangles.append(active.pop(run))
            for run in sorted(present):
                if run in active:
                    active[run][3] += 1
                else:
                    active[run] = [run[0], y, run[1] - run[0], 1]
            if len(rectangles) + len(active) > MAX_SHAPES_PER_FRAME:
                raise SpriteCollisionError("source contains excessive exact collision islands")
        rectangles.extend(active[k] for k in sorted(active))
        rectangles.sort(key=lambda x: (x[1], x[0], x[2], x[3]))
        # Independently rasterize resulting rectangles. Require single coverage
        # of every selected pixel, zero coverage of clear pixels, no overlap.
        rebuilt = [[0 for _ in range(width)] for _ in range(height)]
        for x, y, w, h in rectangles:
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > width or y + h > height:
                raise SpriteCollisionError("compiler emitted invalid rectangle bounds")
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    rebuilt[yy][xx] += 1
        if any(rebuilt[y][x] != int(rows[y][x])
               for y in range(height) for x in range(width)):
            raise SpriteCollisionError("merged hitboxes differ from exact alpha mask")
        total_shapes += len(rectangles)
        if total_shapes > MAX_TOTAL_SHAPES:
            raise SpriteCollisionError("collision rectangles exceed whole-atlas budget")
        pivot = frame.get("pivot_px")
        if (type(pivot) is not list or len(pivot) != 2
                or any(type(value) is not int for value in pivot)):
            raise SpriteCollisionError("hitbox has no authored actor-space pivot")
        scaled = [
            [x * scale - pivot[0], y * scale - pivot[1], w * scale, h * scale]
            for x, y, w, h in rectangles
        ]
        result_frames.append({
            "frame_id": frame["frame_id"],
            "duration_ms": frame["duration_ms"],
            "source_mask_sha256": frame["collision_mask_sha256"],
            "source_opaque_pixels": coverage,
            "pivot_px": list(pivot),
            "exact_source_rects": rectangles,
            "sprite_local_scaled_rects": scaled,
            "rectangle_count": len(rectangles),
            "no_extra_or_missing_collision_pixels": True,
        })
    body = {
        "schema_version": SCHEMA,
        "source_sprite_receipt_sha256": claimed,
        "asset_id": sprite["asset_id"],
        "source_record_id": sprite["record_id"],
        "alpha_threshold": sprite["atlas_geometry"]["alpha_threshold"],
        "source_pixel_scale": scale,
        "frames": result_frames,
        "total_rectangles": total_shapes,
        "all_source_alpha_pixels_reconstructed": True,
        "godot_collision_nodes_instantiated": False,
    }
    body["receipt_sha256"] = digest(body)
    return body


def verify_exact_sprite_hitboxes(
    sprite: Mapping[str, Any], artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently regenerate every rectangle from signed original mask bits."""
    expected = compile_exact_sprite_hitboxes(sprite)
    if not isinstance(artifact, Mapping) or dict(artifact) != expected:
        raise SpriteCollisionError("collision sidecar differs from source alpha topology")
    return expected


__all__ = [
    "SpriteCollisionError", "compile_exact_sprite_hitboxes",
    "verify_exact_sprite_hitboxes",
]
