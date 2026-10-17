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
    SEMANTIC_LENS_BUDGET, EXTENDED_SEMANTIC_LENS_BUDGET,
    route_episode_semantic_lenses,
)

SCHEMA = "skeleton.jeeves.game_triangle_candidate_corpus.v2"
MAX_VIEWS = 8192


class TriangleCorpusError(ValueError):
    pass


def compile_triangle_candidate_corpus(
    evidence: dict[str, Any], triangle: dict[str, Any],
    reviewed: dict[str, Any], *,
    requested_semantic_lens_keys: Sequence[str] = (),
    semantic_inference_review: dict[str, Any] | None = None,
    semantic_inference_reviews: Sequence[dict[str, Any]] = (),
    semantic_lens_budget: int = SEMANTIC_LENS_BUDGET,
) -> dict[str, Any]:
    """Construct data *candidates* for the existing Jeeves corpus governance.

    The real native model's generation must additionally be replayed with
    the actual local checkpoint by the operator before this is stored.
    """
    if type(semantic_lens_budget) is not int or semantic_lens_budget not in (
        SEMANTIC_LENS_BUDGET, EXTENDED_SEMANTIC_LENS_BUDGET,
    ):
        raise TriangleCorpusError("canonical semantic corpus budget must be 43 or 200")
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
    if semantic_inference_review is not None and semantic_inference_reviews:
        raise TriangleCorpusError("single and multi-episode semantic reviews cannot be combined")
    if semantic_inference_reviews and (
            type(semantic_inference_reviews) not in (list, tuple)
            or len(semantic_inference_reviews) != len(episodes)
            or len(episodes) < 2):
        raise TriangleCorpusError("multi-episode semantic corpus requires one review per episode")
    review_batch = (
        (semantic_inference_review,) if semantic_inference_review is not None
        else semantic_inference_reviews
    )
    if review_batch:
        from .game_emulator_triangle_semantic_inference import verify_native_semantic_lenses
        for checked_review in review_batch:
            verify_native_semantic_lenses(evidence, triangle, reviewed, checked_review)
            if (checked_review.get("all_semantic_interpretations_valid") is not True
                    or type(checked_review.get("source_bound_interpretations")) is not int
                    or checked_review["source_bound_interpretations"] != semantic_lens_budget
                    or checked_review.get("native_model_generations_executed") != semantic_lens_budget
                    or checked_review.get("lens_budget", SEMANTIC_LENS_BUDGET) != semantic_lens_budget):
                raise TriangleCorpusError(
                    "all canonical semantic interpretations must be source-linked before export"
                )
            if tuple(checked_review["requested_lens_keys"]) != tuple(requested_semantic_lens_keys):
                raise TriangleCorpusError("semantic model used a different operator-approved lens set")
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
            episode, max_lenses=semantic_lens_budget,
            requested_keys=requested_semantic_lens_keys,
        )
        if routed["source_native_trace_sha256"] != trace:
            raise TriangleCorpusError("canonical semantic route changed native source")
        total_semantic_routes += routed["actually_routed_lenses"]
        semantic_routes.append({
            "native_trace_sha256": trace,
            "canonical_registry": routed.get(
                "canonical_registry",
                "skeleton.jeeves.agent.semantic_maximal.MaximalSemanticRegistry",
            ),
            "canonical_catalog_sha256": routed["canonical_catalog_sha256"],
            "semantic_route_digest": routed["route_digest"],
            "semantic_governance_fingerprint": routed["governance_fingerprint"],
            "selection_mode": routed["selection_mode"],
            "router_observation_fingerprints": routed["observation_fingerprints"],
            "semantic_questions": [{
                "lens_key": view["lens_key"],
                "family": view["lens_family"],
                "activation_score": view["activation_score"],
                "native_evidence_support_class": view["native_evidence_support_class"],
                "matched_native_observation_cues": view["matched_native_observation_cues"],
                "native_observation_cue_provenance_sha256": view[
                    "native_observation_cue_provenance_sha256"
                ],
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
    if semantic_inference_review is not None:
        expected = [
            route for route in semantic_routes
            if route["native_trace_sha256"] == semantic_inference_review["source_native_trace_sha256"]
        ]
        if (len(expected) != 1
                or expected[0]["semantic_route_digest"] != semantic_inference_review["canonical_route_sha256"]):
            raise TriangleCorpusError("executed semantic reviewer used a different episode/lens route")
        semantic_inference_reference = {
            "native_trace_sha256": semantic_inference_review["source_native_trace_sha256"],
            "semantic_review_sha256": semantic_inference_review["semantic_review_digest"],
            "model_sha256": semantic_inference_review["model_sha256"],
            "source_bound_hypotheses": semantic_inference_review["source_bound_interpretations"],
            "exact_checkpoint_generations_verified": semantic_lens_budget,
            "hypotheses_are_ground_truth_labels": False,
            "human_adjudication_still_required": True,
        }
    else:
        semantic_inference_reference = None
    multi_semantic_references = None
    if semantic_inference_reviews:
        route_by_trace = {
            item["native_trace_sha256"]: item for item in semantic_routes
        }
        review_by_trace: dict[str, dict[str, Any]] = {}
        model_ids = set()
        for item in semantic_inference_reviews:
            trace = item["source_native_trace_sha256"]
            model_ids.add(item["model_sha256"])
            if (trace not in route_by_trace or trace in review_by_trace
                    or item["canonical_route_sha256"] !=
                    route_by_trace[trace]["semantic_route_digest"]):
                raise TriangleCorpusError("duplicate, foreign or stale semantic episode review")
            review_by_trace[trace] = item
        if len(review_by_trace) != len(episodes) or len(model_ids) != 1:
            raise TriangleCorpusError("each native episode needs unique semantic review from one checkpoint")
        multi_semantic_references = [{
            "native_trace_sha256": trace,
            "semantic_review_sha256": review_by_trace[trace]["semantic_review_digest"],
            "canonical_route_sha256": route_by_trace[trace]["semantic_route_digest"],
            "model_sha256": review_by_trace[trace]["model_sha256"],
            "source_bound_hypotheses": semantic_lens_budget,
            "hypotheses_are_ground_truth_labels": False,
            "human_adjudication_still_required": True,
        } for trace in [episode["source_trace_sha256"] for episode in episodes]]
    result = {
        "schema_version": (
            "skeleton.jeeves.game_triangle_candidate_corpus.v4"
            if multi_semantic_references is not None else
            "skeleton.jeeves.game_triangle_candidate_corpus.v3"
            if semantic_inference_reference is not None else SCHEMA
        ),
        "native_semantic_inference_reference": semantic_inference_reference,
        **({"native_semantic_inference_references": multi_semantic_references}
           if multi_semantic_references is not None else {}),
        "semantic_model_hypotheses_added_to_supervised_labels": 0,
        "source_emulator_report_sha256": evidence["report_digest"],
        "source_training_triangle_sha256": triangle["triangle_digest"],
        "native_adversarial_review_sha256": reviewed["review_digest"],
        "source_rom_sha256": lineage["source_sha256"],
        "operator_rights_review_id": lineage["rights_review_id"],
        "source_native_episode_count": len(episodes),
        "unique_independent_native_episodes": len(seen),
        "total_lens_candidate_views": len(rows),
        "views_per_original_episode": len(LENSES),
        "canonical_semantic_lens_selection_budget": semantic_lens_budget,
        "operator_requested_semantic_lens_keys": list(requested_semantic_lens_keys),
        "semantic_lens_selection_digest": _digest([
            [route["native_trace_sha256"], route["semantic_route_digest"]]
            for route in semantic_routes
        ]),
        "routed_semantic_lens_questions": total_semantic_routes,
        "semantic_questions_are_not_supervised_labels": True,
        "semantic_lens_activations_do_not_create_reward_or_weight_updates": True,
        "native_semantic_catalog": semantic_routes[0]["canonical_registry"],
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
    reviewed: dict[str, Any], candidate: Any, *,
    semantic_inference_review: dict[str, Any] | None = None,
    semantic_inference_reviews: Sequence[dict[str, Any]] = (),
) -> None:
    if not isinstance(candidate, dict) or candidate.get("candidate_corpus_digest") != _digest({
        k: v for k, v in candidate.items() if k != "candidate_corpus_digest"
    }):
        raise TriangleCorpusError("candidate corpus digest differs")
    if candidate != compile_triangle_candidate_corpus(
        evidence, triangle, reviewed,
        requested_semantic_lens_keys=candidate.get("operator_requested_semantic_lens_keys", ()),
        semantic_inference_review=semantic_inference_review,
        semantic_inference_reviews=semantic_inference_reviews,
        semantic_lens_budget=candidate.get("canonical_semantic_lens_selection_budget", SEMANTIC_LENS_BUDGET),
    ):
        raise TriangleCorpusError("candidate training corpus no longer matches measured source")
