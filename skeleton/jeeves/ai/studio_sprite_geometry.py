"""Strict game-ready sprite atlas packing, masks and resource geometry.

Bounded palette rasterization, deterministic grid placement, optional per-frame
bleed-safe extruded gutters, power-of-two surfaces, alpha hitboxes and pivot
geometry. All source colors are straight-alpha RGBA; no resampling or invented
pixels enter the authored frame interior.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

MAX_TEXTURE_EDGE = 8192
MAX_PIXELS = 1024 * 1024


class AtlasGeometryError(ValueError):
    """Invalid source pixel grid, atlas policy or texture budget."""


def _number(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AtlasGeometryError(name + " exceeds explicit texture bounds")
    return value


def _pot(number: int) -> int:
    return 1 << (number - 1).bit_length()


def layout_policy(
    raw: Any, *, frame_count: int, width: int, height: int, scale: int,
) -> dict[str, Any]:
    if raw is None:
        value = {
            "columns": min(frame_count, max(1, 4096 // (width * scale))),
            "padding_px": 0, "extrude_edges": False,
            "power_of_two": False, "alpha_threshold": 1,
            "pivot_px": [width // 2, height // 2],
        }
    else:
        names = {
            "columns", "padding_px", "extrude_edges",
            "power_of_two", "alpha_threshold", "pivot_px",
        }
        if not isinstance(raw, dict) or set(raw) != names:
            raise AtlasGeometryError("atlas config must explicitly declare all geometry policies")
        value = dict(raw)
    _number(value["columns"], "atlas column count", 1, frame_count)
    _number(value["padding_px"], "frame bleed gutter", 0, 8)
    _number(value["alpha_threshold"], "collision alpha threshold", 1, 255)
    for field in ("extrude_edges", "power_of_two"):
        if type(value[field]) is not bool:
            raise AtlasGeometryError(field + " must be explicitly boolean")
    if value["extrude_edges"] and not value["padding_px"]:
        raise AtlasGeometryError("edge extrusion requires a positive texture gutter")
    pivot = value["pivot_px"]
    if (type(pivot) is not list or len(pivot) != 2
            or type(pivot[0]) is not int or type(pivot[1]) is not int
            or not 0 <= pivot[0] < width or not 0 <= pivot[1] < height):
        raise AtlasGeometryError("per-asset pivot must be inside original pixel frame")
    return value


def rasterize_atlas(
    palette: list[bytes], frames: list[dict[str, Any]],
    *, width: int, height: int, scale: int, policy: dict[str, Any],
) -> dict[str, Any]:
    """Pack exactly authored pixels with deterministic edge guards and hitboxes."""
    count = len(frames)
    col_count = policy["columns"]
    padding = policy["padding_px"]
    frame_w = width * scale
    frame_h = height * scale
    cell_w = frame_w + 2 * padding
    cell_h = frame_h + 2 * padding
    row_count = (count + col_count - 1) // col_count
    raw_width = col_count * cell_w
    raw_height = row_count * cell_h
    full_width = _pot(raw_width) if policy["power_of_two"] else raw_width
    full_height = _pot(raw_height) if policy["power_of_two"] else raw_height
    if (full_width > MAX_TEXTURE_EDGE or full_height > MAX_TEXTURE_EDGE
            or full_width * full_height > MAX_PIXELS):
        raise AtlasGeometryError("original atlas exceeds bounded GPU texture dimensions")
    stride = full_width * 4
    # The buffer starts at transparent black, the only unallocated pixel value.
    pixels_out = bytearray(full_width * full_height * 4)
    metadata = []
    for index, frame in enumerate(frames):
        indices = frame["pixels"]
        if (type(indices) is not list or len(indices) != width * height
                or any(type(pixel) is not int or not 0 <= pixel < len(palette)
                       for pixel in indices)):
            raise AtlasGeometryError("source frame is not an exact palette-index bitmap")
        x0 = (index % col_count) * cell_w + padding
        y0 = (index // col_count) * cell_h + padding
        bounds = [width, height, -1, -1]
        covered = 0
        original = bytearray()
        mask = bytearray((width * height + 7) // 8)
        for y in range(height):
            for x in range(width):
                rgba = palette[indices[y * width + x]]
                original.extend(rgba)
                if rgba[3] >= policy["alpha_threshold"]:
                    covered += 1
                    bounds[0] = min(bounds[0], x)
                    bounds[1] = min(bounds[1], y)
                    bounds[2] = max(bounds[2], x)
                    bounds[3] = max(bounds[3], y)
                    pixel_id = y * width + x
                    mask[pixel_id >> 3] |= 1 << (pixel_id & 7)
        # Optional extrusion is generated from edge pixels only in the outer
        # gutter. Interior pixels remain bit-identical to nearest-neighbor
        # upscaled original RGBA values. Transparent RGB must be zero upstream.
        edge = padding if policy["extrude_edges"] else 0
        for ly in range(-edge, frame_h + edge):
            sample_y = min(height - 1, max(0, ly // scale))
            for lx in range(-edge, frame_w + edge):
                sample_x = min(width - 1, max(0, lx // scale))
                rgba = palette[indices[sample_y * width + sample_x]]
                position = (y0 + ly) * stride + (x0 + lx) * 4
                pixels_out[position:position + 4] = rgba
        opaque = None
        if covered:
            opaque = [
                bounds[0] * scale, bounds[1] * scale,
                (bounds[2] - bounds[0] + 1) * scale,
                (bounds[3] - bounds[1] + 1) * scale,
            ]
        metadata.append({
            "rect_px": [x0, y0, frame_w, frame_h],
            "pivot_px": [
                policy["pivot_px"][0] * scale,
                policy["pivot_px"][1] * scale,
            ],
            "opaque_bounds_px": opaque,
            "opaque_source_pixels": covered,
            "source_pixels": width * height,
            "collision_alpha_threshold": policy["alpha_threshold"],
            "collision_mask_sha256": sha256(mask).hexdigest(),
            "collision_mask_bits_hex": mask.hex(),
            "original_rgba_sha256": sha256(original).hexdigest(),
        })
    return {
        "pixels": bytes(pixels_out),
        "sheet_width_px": full_width, "sheet_height_px": full_height,
        "frame_width_px": frame_w, "frame_height_px": frame_h,
        "frames": metadata,
        "geometry": {
            "columns": col_count, "rows": row_count,
            "cell_width_px": cell_w, "cell_height_px": cell_h,
            "padding_px": padding,
            "extrude_edges": policy["extrude_edges"],
            "power_of_two": policy["power_of_two"],
            "alpha_threshold": policy["alpha_threshold"],
            "source_pivot_px": list(policy["pivot_px"]),
            "unused_trailing_cells": row_count * col_count - count,
            "nearest_neighbor_preserved": True,
            "alpha_encoding": "straight_rgba_no_premultiplication",
        },
    }


__all__ = ["AtlasGeometryError", "layout_policy", "rasterize_atlas"]
