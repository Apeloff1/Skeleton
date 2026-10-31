"""Deterministic pixel-level temporal QA for ORIGINAL animated game sprites.

Works on the decoded straight-alpha RGBA atlas, sampling every original frame
at exact grid positions and authored integer pixel scale. Reports visible
coverage, opacity-weighted centroid, inter-frame pixel/alpha changes and
potential registration jitter. These are objective review signals only:
art direction, copyright and subjective animation quality require humans.
"""
from __future__ import annotations

from hashlib import sha256
from math import isqrt
from typing import Any

from .studio_interaction_contract import digest

MAX_AREA = 1024 * 1024
MAX_FRAMES = 64


class SpriteTemporalError(ValueError):
    """Sprite temporal inspection cannot trust authored frame geometry."""


def temporal_sprite_report(
    rgba: bytes, metadata: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(metadata, dict) or type(rgba) is not bytes:
        raise SpriteTemporalError("temporal check requires real decoded RGBA and source")
    sw, sh = metadata.get("sheet_width_px"), metadata.get("sheet_height_px")
    scale = metadata.get("pixel_scale")
    fw, fh = metadata.get("frame_width_px"), metadata.get("frame_height_px")
    frames = metadata.get("frames")
    if (any(type(x) is not int for x in (sw, sh, scale, fw, fh))
            or sw < 1 or sh < 1 or sw * sh > MAX_AREA
            or len(rgba) != sw * sh * 4
            or not 1 <= scale <= 8
            or not 1 <= fw // scale <= 64 or not 1 <= fh // scale <= 64
            or fw % scale or fh % scale
            or type(frames) is not list or not 1 <= len(frames) <= MAX_FRAMES):
        raise SpriteTemporalError("sprite dimensions or frames cannot be independently measured")
    width, height = fw // scale, fh // scale
    frame_details: list[dict[str, Any]] = []
    last: bytes | None = None
    last_centroid: tuple[int, int] | None = None
    warnings: set[str] = set()
    for index, frame in enumerate(frames):
        rect = frame.get("rect_px") if isinstance(frame, dict) else None
        if (type(rect) is not list or len(rect) != 4
                or any(type(x) is not int for x in rect)
                or rect[2:] != [fw, fh]
                or rect[0] < 0 or rect[1] < 0
                or rect[0] + fw > sw or rect[1] + fh > sh):
            raise SpriteTemporalError("frame rectangle cannot be sampled inside RGBA source")
        sampled = bytearray()
        opacity = 0
        centroid_x = centroid_y = 0
        for y in range(height):
            for x in range(width):
                at = ((rect[1] + y * scale) * sw + rect[0] + x * scale) * 4
                pixel = rgba[at:at + 4]
                sampled.extend(pixel)
                weight = pixel[3]
                opacity += weight
                centroid_x += (2 * x + 1) * weight
                centroid_y += (2 * y + 1) * weight
        source = bytes(sampled)
        centroid = (
            (centroid_x * 500 // opacity, centroid_y * 500 // opacity)
            if opacity else None
        )
        changed = changed_alpha = None
        drift = None
        if last is not None:
            changed = sum(
                source[i:i+4] != last[i:i+4]
                for i in range(0, len(source), 4)
            )
            changed_alpha = sum(
                source[i+3] != last[i+3]
                for i in range(0, len(source), 4)
            )
            if changed == 0:
                warnings.add("duplicate_consecutive_rgba_frames")
            if centroid is not None and last_centroid is not None:
                delta_x = centroid[0] - last_centroid[0]
                delta_y = centroid[1] - last_centroid[1]
                drift = isqrt(delta_x * delta_x + delta_y * delta_y)
                if drift > max(width, height) * 375:
                    warnings.add("large_alpha_centroid_shift_check_art_registration")
        if opacity == 0:
            warnings.add("fully_transparent_authored_frame")
        frame_details.append({
            "frame_id": frame.get("frame_id"),
            "source_order": index,
            "rgba_sha256": sha256(source).hexdigest(),
            "source_pixel_count": width * height,
            "alpha_weight_sum": opacity,
            "alpha_centroid_source_milli_px": (
                list(centroid) if centroid is not None else None
            ),
            "changed_source_pixels_since_prior": changed,
            "changed_alpha_pixels_since_prior": changed_alpha,
            "centroid_step_source_milli_px": drift,
        })
        last = source
        last_centroid = centroid
    result = {
        "schema_version": "skeleton.jeeves.sprite_temporal_pixel_quality.v1",
        "asset_id": metadata.get("asset_id"),
        "decoded_atlas_rgba_sha256": sha256(rgba).hexdigest(),
        "original_frame_count": len(frames),
        "sampled_source_pixel_size": [width, height],
        "per_frame": frame_details,
        "review_warnings": sorted(warnings),
        "full_alpha_and_color_frames_compared": True,
        "human_animation_quality_review_complete": False,
        "native_frame_rendering_observed": False,
    }
    result["receipt_sha256"] = digest(result)
    return result


__all__ = ["SpriteTemporalError", "temporal_sprite_report"]
