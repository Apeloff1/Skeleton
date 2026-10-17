"""Candidate Jeeves training-data views from verified emulator triangle evidence.

Eight measured views and up to 43 canonical semantic lens questions are
created for each independently measured native episode. The semantic questions
are not target labels. The measured views retain their original custody.
episode. These are correlated views of ONE episode, NOT eight extra source
games or eight independent rewards. The untrusted local LLM review is a gating
input but never copied into target labels. This does not run transformer SGD.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from .game_emulator_triangle import LENSES, verify_training_triangle
from .game_emulator_triangle_native_reviewer import verify_native_adversarial_review
from .game_learning import _digest
from .game_emulator_triangle_semantics import (
    SEMANTIC_LENS_BUDGET, route_episode_semantic_lenses,
)

SCHEMA = "skeleton.jeeves.game_triangle_candidate_corpus.v1"
MAX_VIEWS = 8192


class TriangleCorpusError(ValueError):
    pass


def compile_triangle_candidate_corpus(
    evidence: dict[str, Any], triangle: dict[str, Any],
    reviewed: dict[str, Any], *,
    requested_semantic_lens_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Construct data *candidates* for the existing Jeeves corpus governance.

    The real native model's generation must additionally be replayed with
    the actual local checkpoint by the operator before this is stored.
    """
    verify_training_triangle(evidence, triangle)
    verify_native_adversarial_review(evidence, triangle, reviewed)
    if reviewed.get("structured_source_bound_passes") != 3:
        raise TriangleCorpusError(
            "all three adversarial challenges need validated source references"
        )
    lineage = evidence.get("source_lineage")
    if (type(lineage) is not dict
            or lineage.get("rights_acknowledged") is not True
            or type(lineage.get("source_sha256")) is not str
            or len(lineage["source_sha256"]) != 64
            or type(lineage.get("rights_review_id")) is not str
            or len(lineage["rights_review_id"].strip()) < 5):
        raise TriangleCorpusError("operator-rights-cleared native source required")
    episodes = triangle["episode_lens_references"]
    if not 1 <= len(episodes) <= 1024 or len(episodes) * len(LENSES) > MAX_VIEWS:
        raise TriangleCorpusError("candidate training lens count exceeds bounds")
    rows: list[dict[str, Any]] = []
    semantic_routes: list[dict[str, Any]] = []
    total_semantic_routes = 0
    seen: set[str] = set()
    for episode in episodes:
        trace = episode["source_trace_sha256"]
        if trace in seen:
            raise TriangleCorpusError("repeated native episode cannot multiply independent examples")
        seen.add(trace)
        measured = episode["grounded_lens_evidence"]
        routed = route_episode_semantic_lenses(
            episode, max_lenses=SEMANTIC_LENS_BUDGET,
            requested_keys=requested_semantic_lens_keys,
        )
        if routed["source_native_trace_sha256"] != trace:
            raise TriangleCorpusError("canonical semantic route changed native source")
        total_semantic_routes += routed["actually_routed_lenses"]
        semantic_routes.append({
            "native_trace_sha256": trace,
            "canonical_catalog_sha256": routed["canonical_catalog_sha256"],
            "semantic_route_digest": routed["route_digest"],
            "semantic_governance_fingerprint": routed["governance_fingerprint"],
            "selection_mode": routed["selection_mode"],
            "router_observation_fingerprints": routed["observation_fingerprints"],
            "semantic_questions": [{
                "lens_key": view["lens_key"],
                "family": view["lens_family"],
                "activation_score": view["activation_score"],
                "question": view["question"],
                "governance_grade": view["governance_grade"],
                "governance_fingerprint": view["governance_fingerprint"],
                "factual_claims_allowed": False,
                "causal_claims_allowed": False,
                "interpretive_question_not_training_ground_truth": True,
                "state": "not_measured_pending_independent_review",
                "factual_label_available": False,
            } for view in routed["routes"]],
        })
        if set(measured) != set(LENSES):
            raise TriangleCorpusError("all eight source-measured lenses are required")
        for lens in LENSES:
            payload = measured[lens]
            if type(payload) is not dict:
                raise TriangleCorpusError("candidate training lens lacks grounded numeric evidence")
            # Neither original ROM bytes nor separately generated criticism are
            # embedded in supervised target text. Numeric evidence is bounded.
            source = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
            if len(source.encode()) > 2000:
                raise TriangleCorpusError("candidate source lens payload exceeds budget")
            view_id = _digest([triangle["triangle_digest"], trace, lens])
            row = {
                "candidate_id": "game-triangle-" + view_id[:32],
                "gameplay_trace_sha256": trace,
                "source_receipt_sha256": episode["source_receipt_sha256"],
                "verified_native_episode_steps": episode["unique_source_transitions"],
                "lens": lens,
                "prompt": (
                    "Using only native emulator evidence from gameplay trace "
                    + trace + ", report the measured " + lens.replace("_", " ")
                    + " perspective. Do not infer a game victory, narrative or "
                    "an unobserved mechanic. Quote the evidence as source data."
                ),
                "answer": (
                    "Source-verified native emulator measurements for " + lens
                    + ": " + source
                    + ". Additional independent gameplay samples from this view: 0."
                ),
                "label_origin": "deterministic_native_evidence_projection",
                "shared_source_group_sha256": trace,
                "same_source_view_weight": {
                    "numerator": 1, "denominator": len(LENSES),
                },
                "training_split": "candidate_train_only",
                "not_for_heldout_evaluation": True,
                "gameplay_success_claimed": False,
                "training_effect_executed": False,
            }
            row["row_digest"] = _digest(row)
            rows.append(row)
    result = {
        "schema_version": SCHEMA,
        "source_emulator_report_sha256": evidence["report_digest"],
        "source_training_triangle_sha256": triangle["triangle_digest"],
        "native_adversarial_review_sha256": reviewed["review_digest"],
        "source_rom_sha256": lineage["source_sha256"],
        "operator_rights_review_id": lineage["rights_review_id"],
        "source_native_episode_count": len(episodes),
        "unique_independent_native_episodes": len(seen),
        "total_lens_candidate_views": len(rows),
        "views_per_original_episode": len(LENSES),
        "canonical_semantic_lens_selection_budget": SEMANTIC_LENS_BUDGET,
        "operator_requested_semantic_lens_keys": list(requested_semantic_lens_keys),
        "semantic_lens_selection_digest": _digest([
            [route["native_trace_sha256"], route["semantic_route_digest"]]
            for route in semantic_routes
        ]),
        "routed_semantic_lens_questions": total_semantic_routes,
        "semantic_questions_are_not_supervised_labels": True,
        "semantic_lens_activations_do_not_create_reward_or_weight_updates": True,
        "native_semantic_catalog": "skeleton.jeeves.agent.semantic_maximal",
        "semantic_routes_per_episode": semantic_routes,
        "same_source_total_weight_per_episode": 1.0,
        "additional_independent_gameplay_episodes_from_lenses": 0,
        "adversarial_generated_text_used_as_training_labels": False,
        "heldout_native_evaluation_steps_imported": 0,
        "reviewer_model_output_factually_adjudicated": False,
        "operator_admission_to_jeeves_corpus_required": True,
        "production_jeeves_optimizer_steps": 0,
        "candidate_rows": rows,
    }
    result["candidate_corpus_digest"] = _digest(result)
    return result


def verify_triangle_candidate_corpus(
    evidence: dict[str, Any], triangle: dict[str, Any],
    reviewed: dict[str, Any], candidate: Any,
) -> None:
    if not isinstance(candidate, dict) or candidate.get("candidate_corpus_digest") != _digest({
        k: v for k, v in candidate.items() if k != "candidate_corpus_digest"
    }):
        raise TriangleCorpusError("candidate corpus digest differs")
    if candidate != compile_triangle_candidate_corpus(
        evidence, triangle, reviewed,
        requested_semantic_lens_keys=candidate.get("operator_requested_semantic_lens_keys", ()),
    ):
        raise TriangleCorpusError("candidate training corpus no longer matches measured source")
