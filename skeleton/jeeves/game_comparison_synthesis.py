"""Evidence-grounded game synthesis and ten-title training curriculum proposals.

This never labels game quality, wisdom or parameter gain as proven by image
hashes. Objective metrics remain objective; notes are authored hypotheses.
The output is a *curriculum proposal* for an independent training owner, not
model training itself.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import digest

SCHEMA = "skeleton.game.comparative_synthesis.v1"
MAX_TITLES_PER_TRAINING_COHORT = 10


def synthesize_comparative_report(report: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_version") != "skeleton.game.comparative_study_result.v1":
        raise ValueError("Only actual canonical comparative study reports may propose synthesis")
    games = report["games"]
    if not isinstance(games, dict) or len(games) > 30:
        raise ValueError("Comparative synthesis exceeds thirty distinct game variants")
    actual = [g for g in games.values() if g.get("status") == "actual_native_observations_captured"]
    dimensions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    proposals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in report.get("observer_notes", []):
        if note.get("knowledge_status") != "reviewed_observation_candidate":
            continue
        entry = {
            "note_id": note["note_id"],
            "author": note["author"],
            "source_game_ids": note["game_ids"],
            "claim_type": note["claim_type"],
            "review_status": note["review_status"],
            "dimension": note["dimension"],
            "text": note["text"],
            "evidence": note["evidence"],
            "independently_verified": False,
            "safe_for_automatic_content_copying": False,
        }
        dimensions[note["dimension"]].append(entry)
        parameter = note.get("build_parameter_candidate")
        if parameter is not None:
            proposals[parameter["name"]].append({
                "candidate": parameter,
                "note_id": note["note_id"],
                "evidence": note["evidence"],
                "human_review": "local_review_only",
                "verified_in_held_out_gameplay": False,
            })
    parameter_matrix = []
    for name, variants in sorted(proposals.items()):
        values = {(item["candidate"]["value"], item["candidate"]["units"]) for item in variants}
        parameter_matrix.append({
            "parameter_name": name,
            "proposal_count": len(variants),
            "candidate_values": variants,
            "conflicting_values_or_units": len(values) > 1,
            "recommendation": "experiment_in_shadow_builder_and_verify" if len(values) == 1
                else "resolve_disagreement_by_independent_comparisons",
            "may_promote_to_production": False,
        })
    objective = []
    for pair in report.get("pairs", []):
        if pair.get("status") != "paired_native_observations_available":
            continue
        objective.append({
            "left_id": pair["left_id"], "right_id": pair["right_id"],
            "source": "actual_native_telemetry_comparison",
            "phases": [
                {
                    "phase": p["phase"],
                    "brightness_difference": p["screen_mean_absolute_difference"],
                    "audio_rms_difference": p["audio_rms_absolute_difference"],
                    "same_pixel_bytes": p["same_exact_frame_sha256"],
                    "same_pcm_bytes": p["same_exact_audio_sha256"],
                    "non_reconstructive_av_texture_differences": p.get("non_reconstructive_signal_texture_differences", {}),
                    "evidence_refs": [p["left_evidence_ref"], p["right_evidence_ref"]],
                    "same_gameplay_quality": None,
                }
                for p in pair["phase_comparisons"]
            ],
            "meaning": "Measured audiovisual difference only; game mechanics, emotion and quality require annotated independent review",
        })
    # Ten-title cohorts are proposals to train on receipts only after a separate
    # source-rights check and verified compatibility on the production machine.
    cohorts = []
    for first in range(0, len(actual), MAX_TITLES_PER_TRAINING_COHORT):
        rows = actual[first:first + MAX_TITLES_PER_TRAINING_COHORT]
        cohorts.append({
            "cohort_index": len(cohorts),
            "game_ids": [g["id"] for g in rows],
            "game_count": len(rows),
            "native_trace_receipts": [g["canonical_offline_trace_sha256"] for g in rows],
            "objective": "review_corresponding_native_action_frame_audio_receipts",
            "validation": "needs_rights_proof_and_independent_heldout_reference",
            "learning_types_proposed": [
                "input_to_visual_transition_model", "audio_visual_consistency",
                "series_differences", "multi_game_generalization",
            ],
            "training_ready": False,
            "weights_updated": False,
        })
    result = {
        "schema_version": SCHEMA,
        "study_id": report["study_id"],
        "successful_native_game_count": len(actual),
        "study_local_q_learning_games": report.get("games_with_study_local_q_updates", 0),
        "study_local_q_policy_snapshot_receipts": [
            {
                "game_id": game["id"],
                "policy_snapshot_sha256": game["study_local_tabular_training"]["trained_policy_sha256"],
                "q_weight_updates": game["study_local_tabular_training"]["updates_applied"],
                "verified_offline_trace_sha256": game["canonical_offline_trace_sha256"],
                "production_merged": False,
            }
            for game in actual if game.get("study_local_tabular_training") is not None
        ],
        "ten_game_training_cohort_count": len(cohorts),
        "training_cohorts": cohorts,
        "objective_pairwise_metric_findings": objective,
        "observer_authored_insight_dimensions": [
            {"dimension": key, "claim_count": len(value), "claims": value}
            for key, value in sorted(dimensions.items())
        ],
        "build_parameter_hypotheses": parameter_matrix,
        "cross_series_synthesis_policy": (
            "Combine generalizable mechanics and independently measured parameters, "
            "not protected art, audio, level layouts, character likeness, dialogue or story expression."
        ),
        "insights_source": "native audiovisual telemetry and locally reviewed attributed observers",
        "wisdom_or_semantic_understanding_automatically_established": False,
        "dragon_custody_review_complete": False,
        "automatic_model_training_performed": False,
        "production_model_weights_promoted": False,
    }
    result["synthesis_sha256"] = digest(result)
    return result
