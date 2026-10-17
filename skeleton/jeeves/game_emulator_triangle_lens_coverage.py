"""Read-only, source-bound coverage audit of the actual forty-three Jeeves lenses.

Every run is routed using MaximalSemanticRegistry and scientific governance.
This audit reports observed activation cues, unanswered questions and
possible additional measurements. It never treats 43 lenses as 43 sensors,
fabricates video meaning or performs model inference/production training.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .game_emulator_triangle import verify_training_triangle
from .game_emulator_triangle_semantics import (
    SEMANTIC_LENS_BUDGET, route_episode_semantic_lenses,
)
from .game_learning import _digest

SCHEMA = "skeleton.jeeves.game_triangle_43_lens_coverage.v1"
MAX_EPISODES_PER_PAGE = 16


class TriangleCoverageError(ValueError):
    """Invalid source, routing identity, or pagination cannot produce coverage."""


def audit_43_lens_coverage(
    evidence: dict[str, Any], triangle: dict[str, Any], *,
    start_episode: int = 0, limit: int = 8,
    requested_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Route EXACTLY 43 governed questions for each admitted native episode."""
    verify_training_triangle(evidence, triangle)
    episodes = triangle["episode_lens_references"]
    if (type(start_episode) is not int or not 0 <= start_episode < len(episodes)
            or type(limit) is not int or not 1 <= limit <= MAX_EPISODES_PER_PAGE
            or type(requested_keys) not in (tuple, list)
            or len(requested_keys) not in (0, SEMANTIC_LENS_BUDGET)
            or len(set(requested_keys)) != len(requested_keys)):
        raise TriangleCoverageError("invalid 43-lens audit episode page or lens selection")
    selected = episodes[start_episode:start_episode + limit]
    cover: dict[str, dict[str, Any]] = {}
    episode_rows: list[dict[str, Any]] = []
    catalogue = None
    for i, episode in enumerate(selected, start_episode):
        route = route_episode_semantic_lenses(
            episode, max_lenses=SEMANTIC_LENS_BUDGET,
            requested_keys=requested_keys,
        )
        lenses = route["routes"]
        if (route["actually_routed_lenses"] != SEMANTIC_LENS_BUDGET
                or len(lenses) != SEMANTIC_LENS_BUDGET
                or len({x["lens_key"] for x in lenses}) != SEMANTIC_LENS_BUDGET
                or route["source_native_trace_sha256"] != episode["source_trace_sha256"]
                or route["source_native_receipt_sha256"] != episode["source_receipt_sha256"]
                or route["factual_assertions_authorized"] is not False
                or route["causal_assertions_authorized"] is not False):
            raise TriangleCoverageError("canonical 43-lens routing lost source/governance")
        digest = route["canonical_catalog_sha256"]
        if catalogue is not None and catalogue != digest:
            raise TriangleCoverageError("canonical catalog changed between episode passes")
        catalogue = digest
        supported = []
        hypothesis_only = []
        for row in lenses:
            key = row["lens_key"]
            if (row["new_independent_evidence"] != 0
                    or row["training_ground_truth_label_available"] is not False
                    or row["factual_claims_allowed"] is not False
                    or row["causal_claims_allowed"] is not False
                    or row["native_evidence_support_class"] not in (
                        "measured_native_cue_present",
                        "hypothesis_only_without_matching_native_cue",
                    )):
                raise TriangleCoverageError("a routed lens attempted independent truth promotion")
            hit = row["native_evidence_support_class"] == "measured_native_cue_present"
            if bool(row["matched_native_observation_cues"]) != hit:
                raise TriangleCoverageError("cue support disagrees with native observation evidence")
            if key not in cover:
                cover[key] = {
                    "lens_key": key,
                    "family": row["lens_family"],
                    "governance_grade": row["governance_grade"],
                    "governance_fingerprint": row["governance_fingerprint"],
                    "question": row["question"],
                    "native_cue_supported_episodes": 0,
                    "hypothesis_only_episodes": 0,
                    "native_observation_cue_links": 0,
                    "supported_trace_sha256": [],
                }
            entry = cover[key]
            if (entry["governance_fingerprint"] != row["governance_fingerprint"]
                    or entry["question"] != row["question"]):
                raise TriangleCoverageError("lens governance changed within a frozen audit")
            if hit:
                supported.append(key)
                entry["native_cue_supported_episodes"] += 1
                entry["supported_trace_sha256"].append(episode["source_trace_sha256"])
            else:
                hypothesis_only.append(key)
                entry["hypothesis_only_episodes"] += 1
            entry["native_observation_cue_links"] += len(
                row["native_observation_cue_provenance"]
            )
        if len(supported) + len(hypothesis_only) != SEMANTIC_LENS_BUDGET:
            raise TriangleCoverageError("lens coverage count differs")
        visual = episode["companion_viewing"]["native_rgb24_frames_optically_inspected"]
        counter = episode["ai_playing"]["counterfactual_native_probes"]
        # A missing modality can motivate a NEW measurement. No lens can
        # certify a causal hypothesis from a replay or visual tile hash.
        next_measurements = []
        if visual == 0:
            next_measurements.append("capture_native_rgb24_frames_with_dragon_consent")
        if counter == 0:
            next_measurements.append("execute_approved_alternate_action_native_probes")
        if hypothesis_only:
            next_measurements.append("gather_independent_positive_native_observation_cues")
        episode_rows.append({
            "native_episode_index": i,
            "native_trace_sha256": episode["source_trace_sha256"],
            "source_receipt_sha256": episode["source_receipt_sha256"],
            "canonical_route_sha256": route["route_digest"],
            "governance_sha256": route["governance_fingerprint"],
            "routed_lens_count": SEMANTIC_LENS_BUDGET,
            "cue_supported_lens_keys": supported,
            "hypothesis_only_lens_keys": hypothesis_only,
            "native_rgb24_optical_frames": visual,
            "actual_counterfactual_probes": counter,
            "next_measurement_suggestions": next_measurements,
            "additional_independent_native_training_examples": 0,
            "semantic_proposals_factually_verified": False,
        })
    next_index = start_episode + len(selected)
    report = {
        "schema_version": SCHEMA,
        "parent_emulator_report_sha256": evidence["report_digest"],
        "parent_triangle_sha256": triangle["triangle_digest"],
        "canonical_catalog_sha256": catalogue,
        "operator_pinned_lens_keys": list(requested_keys),
        "start_episode": start_episode,
        "requested_limit": limit,
        "episodes_audited": len(selected),
        "next_episode_index": next_index if next_index < len(episodes) else None,
        "native_gameplay_episodes_created": 0,
        "semantic_model_generations_executed": 0,
        "independent_sample_multiplication": 0,
        "native_cue_supported_lens_exposures": sum(
            len(x["cue_supported_lens_keys"]) for x in episode_rows
        ),
        "hypothesis_only_lens_exposures": sum(
            len(x["hypothesis_only_lens_keys"]) for x in episode_rows
        ),
        "unique_canonical_lenses_routed": len(cover),
        "lens_coverage": [cover[key] for key in sorted(cover)],
        "episode_coverage": episode_rows,
        "factual_or_causal_claims_from_lenses_authorized": False,
        "operator_review_required_for_research": True,
        "production_jeeves_weight_updates": 0,
    }
    report["audit_digest"] = _digest(report)
    return report


def verify_43_lens_coverage(
    evidence: dict[str, Any], triangle: dict[str, Any], saved: Any,
) -> None:
    if type(saved) is not dict or saved.get("audit_digest") != _digest({
        k: v for k, v in saved.items() if k != "audit_digest"
    }):
        raise TriangleCoverageError("43-lens coverage audit SHA-256 differs")
    rebuilt = audit_43_lens_coverage(
        evidence, triangle, start_episode=saved.get("start_episode"),
        limit=saved.get("requested_limit"),
        requested_keys=saved.get("operator_pinned_lens_keys"),
    )
    if saved != rebuilt:
        raise TriangleCoverageError("43-lens coverage is not reproducible against actual native evidence")
