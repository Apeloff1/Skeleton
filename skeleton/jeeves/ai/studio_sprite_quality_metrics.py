"""Reproducible objective quality inspection for original Jeeves sprite assets.

Quantifies correct art-production constraints without pretending to judge taste,
copyright originality or artistic excellence. Source audit may require a human
art director to resolve flagged visual risks before final asset promotion.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .studio_interaction_contract import digest


class SpriteQualityError(ValueError):
    """Sprite quality score cannot be computed from reviewed atlas evidence."""


def sprite_quality_metrics(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic objective score, potential defects and atlas utilization."""
    if not isinstance(metadata, Mapping):
        raise SpriteQualityError("bounded reviewed atlas proof required")
    frames = metadata.get("frames")
    states = metadata.get("animations")
    geometry = metadata.get("atlas_geometry")
    if (not isinstance(frames, list) or not frames
            or not isinstance(states, list) or not states
            or not isinstance(geometry, Mapping)):
        raise SpriteQualityError("quality metrics require pixel and animation evidence")
    fw = metadata.get("frame_width_px")
    fh = metadata.get("frame_height_px")
    sw = metadata.get("sheet_width_px")
    sh = metadata.get("sheet_height_px")
    if (any(type(value) is not int or value <= 0 for value in (fw, fh, sw, sh))
            or sw * sh > 1024 * 1024
            or len(frames) > 64):
        raise SpriteQualityError("source atlas dimensions exceed observable quality bounds")
    used = sum(fw * fh for _ in frames)
    total = sw * sh
    coverage = sum(item["opaque_source_pixels"] for item in frames)
    source_total = sum(item["source_pixels"] for item in frames)
    if source_total <= 0 or coverage > source_total:
        raise SpriteQualityError("collision-alpha occupancy values are invalid")
    unique_frames = len({item["original_rgba_sha256"] for item in frames})
    holds = [item["duration_ms"] for item in frames]
    warnings: list[str] = []
    if coverage == 0:
        warnings.append("all_frames_transparent")
    if len(frames) > 1 and unique_frames == 1:
        warnings.append("no_visible_animation_frame_variation")
    if coverage > 0 and coverage * 50 < source_total:
        warnings.append("very_low_occupied_art_area")
    if used * 4 < total:
        warnings.append("inefficient_texture_utilization")
    if max(holds) >= 30000:
        warnings.append("very_long_single_frame_hold")
    if (geometry["padding_px"] == 0 and len(frames) > 1
            and not geometry["extrude_edges"]):
        warnings.append("texture_filter_bleed_risk_without_gutters")
    score = max(0, 100 - sum({
        "all_frames_transparent": 30,
        "no_visible_animation_frame_variation": 12,
        "very_low_occupied_art_area": 7,
        "inefficient_texture_utilization": 6,
        "very_long_single_frame_hold": 5,
        "texture_filter_bleed_risk_without_gutters": 4,
    }[name] for name in warnings))
    report = {
        "schema_version": "skeleton.jeeves.sprite_objective_quality.v1",
        "asset_id": metadata.get("asset_id"),
        "frame_count": len(frames),
        "animation_state_count": len(states),
        "unique_rgba_frame_count": unique_frames,
        "visible_source_pixels": coverage,
        "total_source_pixels": source_total,
        "alpha_coverage_millionths": coverage * 1_000_000 // source_total,
        "atlas_utilization_millionths": used * 1_000_000 // total,
        "longest_authored_frame_ms": max(holds),
        "verified_alpha_collision_masks": len(frames),
        "objective_risk_flags": warnings,
        "objective_quality_score_0_100": score,
        "manual_art_review_complete": False,
        "originality_and_copyright_review_complete": False,
        "subjective_artistic_quality_proven": False,
    }
    report["receipt_sha256"] = digest(report)
    return report


__all__ = ["SpriteQualityError", "sprite_quality_metrics"]
