"""Deterministic, review-only game asset design findings.

Metrics are reproducible measurements, not aesthetic truth or an LLM's
learned parameters. Nothing original/copyrighted is serialized as samples.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

QUALITY_SCHEMA = "skeleton.game.authorized_decompilation_quality_brief.v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                   allow_nan=False).encode()
    ).hexdigest()


def derive_game_quality_brief(
    *,
    game_format: str,
    source_sha256: str,
    rights_evidence_digest: str,
    asset_analysis: Mapping[str, Any] | None,
    code_analysis: Mapping[str, Any] | None,
    package_analysis: Mapping[str, Any] | None = None,
    human_review_required: bool = True,
) -> dict[str, Any]:
    """Produce original-design improvement questions from authorized measurements."""
    if (type(game_format) is not str or not game_format
        or any(type(x) is not str or len(x) != 64
               or any(ch not in "0123456789abcdef" for ch in x)
               for x in (source_sha256, rights_evidence_digest))
        or human_review_required is not True):
        raise ValueError("Quality brief requires exact source rights and human review")
    findings: list[dict[str, Any]] = []
    features: dict[str, int | float] = {}
    if asset_analysis and asset_analysis.get("chr_present") is True:
        tiles = sum(r["statistics"]["tiles"] for r in asset_analysis["regions"])
        unique = sum(r["statistics"]["unique_tile_sha256"] for r in asset_analysis["regions"])
        dup = sum(r["statistics"]["exact_duplicate_tile_count"] for r in asset_analysis["regions"])
        # Exact counts are per bank; cross-bank uniqueness requires a separate dedupe pass.
        density = round(sum(
            r["statistics"]["edge_density_over_possible_neighbors"] * r["statistics"]["tiles"]
            for r in asset_analysis["regions"]
        ) / max(1, tiles), 5)
        features.update(chr_tile_count=tiles, bank_local_unique_tile_count=unique,
                        bank_local_duplicate_count=dup, graphic_edge_density=density)
        findings.append({
            "dimension": "tile_reuse_and_readability",
            "observed": {"bank_local_duplicate_ratio": round(dup / max(1, tiles), 4),
                         "edge_density": density},
            "design_question": (
                "Can original authored tiles use deliberate reusable motifs while "
                "improving contrast, silhouettes and pixel-grid consistency?"
            ),
            "interpretation_limit": "No identified characters, objects, sprites, layers, animations or gameplay merit",
        })
        findings.append({
            "dimension": "palette_color_communication",
            "observed": {"known_palette_from_rom_header": False},
            "design_question": (
                "Build an original accessible palette with perceptually distinct states; "
                "validate it against authored backgrounds and intended display profiles."
            ),
            "interpretation_limit": "The grayscale tile preview is not the original game's palette",
        })
    elif asset_analysis and asset_analysis.get("chr_ram_cannot_be_recovered_from_static_rom"):
        findings.append({
            "dimension": "runtime_generated_graphics",
            "observed": {"static_chr_rom_available": False},
            "design_question": (
                "Collect authorized runtime PPU/framebuffer evidence for graphics "
                "constructed in RAM; the cartridge header alone reveals no sprite atlas."
            ),
            "interpretation_limit": "No runtime CHR RAM extraction performed",
        })
    if code_analysis and code_analysis.get("instructions_emitted", 0):
        count = code_analysis["instructions_emitted"]
        edges = len(code_analysis.get("control_flow_edges", []))
        features.update(reachable_static_instruction_count=count,
                        static_control_flow_edge_count=edges)
        findings.append({
            "dimension": "state_and_branch_complexity",
            "observed": {
                "bounded_reachable_instruction_count": count,
                "bounded_static_edge_count": edges,
            },
            "design_question": (
                "For your original game, make transitions testable, keep branching "
                "states explicit and check reset/replay determinism."
            ),
            "interpretation_limit": (
                "Static opcode counts do not reveal dialogue quality, game logic "
                "correctness, AI sophistication or shipped source code."
            ),
        })
    if asset_analysis and asset_analysis.get("pixel_count") is not None:
        pixels = asset_analysis["pixel_count"]
        uncovered = asset_analysis.get("nonopaque_pixel_count", 0)
        if (type(pixels) is int and 1 <= pixels <= 1024 * 1024
            and type(uncovered) is int and 0 <= uncovered <= pixels):
            features.update(
                decoded_image_pixels=pixels,
                nonopaque_pixel_fraction=round(uncovered / pixels, 6),
            )
            findings.append({
                "dimension": "original_image_legibility",
                "observed": {
                    "pixel_count": pixels,
                    "nonopaque_pixel_ratio": round(uncovered / pixels, 6),
                    "rgba_sha256": asset_analysis.get("rgba_sha256"),
                },
                "design_question": (
                    "Review the original authored art at target display scale "
                    "for silhouette clarity, aliasing, contrast, transparency "
                    "fringing and accessibility."
                ),
                "interpretation_limit": "Pixel dimensions and alpha do not independently judge artistic quality",
            })
    if asset_analysis and asset_analysis.get("format") == "pcm_wav":
        rate = asset_analysis.get("sample_rate")
        seconds = asset_analysis.get("duration_seconds")
        if (type(rate) is int and 8000 <= rate <= 96000
            and type(seconds) in (int,float) and 0 <= seconds <= 10):
            features.update(audio_sample_rate=rate, audio_duration_seconds=round(seconds,6))
            findings.append({
                "dimension": "original_audio_clarity",
                "observed": {"sample_rate":rate, "duration_seconds":seconds},
                "design_question": (
                    "Audition original authored sound effects against cutscenes, "
                    "input feedback and ambience for readability and clipping."
                ),
                "interpretation_limit": "Duration and sample rate are not fidelity or musical quality scores",
            })
    if package_analysis:
        inventory = package_analysis.get("resource_inventory", [])
        counts = {}
        for row in inventory:
            kind = row["resource_kind"]
            counts[kind] = counts.get(kind, 0) + 1
        features["packaged_resource_count"] = len(inventory)
        findings.append({
            "dimension": "pipeline_completeness",
            "observed": {"file_kind_counts": counts},
            "design_question": (
                "Track each original sprite, scene, sound and script through "
                "asset provenance, revision history and independent playtest receipts."
            ),
            "interpretation_limit": "File types alone are not verified usability or asset quality",
        })
    if not findings:
        findings.append({
            "dimension": "evidence_gap",
            "observed": {"supported_semantic_asset_decoding": False},
            "design_question": (
                "Provide a documented authorized content layout, authored level "
                "map or runtime capture before inferring game asset qualities."
            ),
            "interpretation_limit": "Unknown executable/resource formats are not silently decoded",
        })
    body = {
        "schema_version": QUALITY_SCHEMA,
        "source_sha256": source_sha256,
        "rights_evidence_digest": rights_evidence_digest,
        "format": game_format,
        "measured_numeric_features": features,
        "findings": findings,
        "raw_game_assets_included": False,
        "reconstructed_source_code_included": False,
        "model_training_performed": False,
        "weights_or_parameters_changed": False,
        "original_game_remake_or_clone_authorized": False,
        "human_review_required": True,
        "production_weight_promotion_allowed": False,
        "quality_improvement_verified": False,
    }
    body["brief_digest"] = _digest(body)
    return body
