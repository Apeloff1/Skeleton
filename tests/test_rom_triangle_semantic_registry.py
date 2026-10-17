"""Actual canonical Jeeves semantic catalog integration for native gameplay."""
from __future__ import annotations

import copy

import pytest

from skeleton.jeeves.game_emulator_triangle_semantics import (
    SEMANTIC_LENS_BUDGET, TriangleSemanticError,
    route_episode_semantic_lenses, verify_episode_semantic_lenses,
)


def _episode():
    return {
        "source_trace_sha256": "a" * 64,
        "source_receipt_sha256": "b" * 64,
        "grounded_lens_evidence": {
            "controller_action": {"action_sequence_sha256": "c" * 64},
            "reward_and_consequence": {
                "measured_reward_sequence_sha256": "d" * 64
            },
        },
        "companion_viewing": {
            "native_rgb24_frames_optically_inspected": 3,
            "frame_sequence_sha256": "e" * 64,
            "audio_sequence_sha256": "f" * 64,
        },
        "ai_playing": {
            "actual_native_steps": 3,
            "actual_q_table_updates": 3,
            "counterfactual_native_probes": 1,
            "controller_only_probes": 0,
        },
        "repetition": {
            "replayed_native_steps": 3,
            "reverse_checkpoint_count": 1,
        },
    }


def test_real_jeeves_semantic_router_selects_all_43_governed_questions():
    native = _episode()
    result = route_episode_semantic_lenses(native)
    assert result["requested_max_lenses"] == SEMANTIC_LENS_BUDGET == 43
    assert result["actually_routed_lenses"] == 43
    assert result["canonical_catalog_lens_count"] >= 43
    assert result["canonical_registry"].endswith("MaximalSemanticRegistry")
    assert result["selection_mode"] == "canonical_dynamic_router"
    assert result["semantic_lenses_remain_hypotheses_not_source_evidence"] is True
    assert result["factual_assertions_authorized"] is False
    assert result["causal_assertions_authorized"] is False
    assert result["additional_native_training_examples"] == 0
    assert len(result["governance_fingerprint"]) == 64
    assert len({item["lens_key"] for item in result["routes"]}) == 43
    assert all(item["governance_grade"]
               and item["governance_fingerprint"]
               and item["factual_claims_allowed"] is False
               and item["causal_claims_allowed"] is False
               and item["training_ground_truth_label_available"] is False
               for item in result["routes"])
    verify_episode_semantic_lenses(native, result)


def test_exact_operator_43_key_selection_is_pinned_to_existing_lens_catalog():
    native = _episode()
    selected = route_episode_semantic_lenses(native)
    keys = tuple(item["lens_key"] for item in selected["routes"])
    custom = route_episode_semantic_lenses(native, requested_keys=keys)
    assert custom["selection_mode"] == "operator_exact_43"
    assert custom["operator_requested_lens_keys"] == list(keys)
    assert tuple(row["lens_key"] for row in custom["routes"]) == keys
    assert custom["canonical_catalog_sha256"] == selected["canonical_catalog_sha256"]
    verify_episode_semantic_lenses(native, custom)


def test_unknown_or_duplicate_custom_lens_fails_without_fallback():
    native = _episode()
    selected = route_episode_semantic_lenses(native)
    keys = [item["lens_key"] for item in selected["routes"]]
    with pytest.raises(TriangleSemanticError, match="43 unique"):
        route_episode_semantic_lenses(
            native, requested_keys=keys[:-1] + [keys[0]],
        )
    with pytest.raises(TriangleSemanticError, match="missing"):
        route_episode_semantic_lenses(
            native, requested_keys=keys[:-1] + ["nonexistent_test_lens_12345"],
        )


def test_saved_governed_question_or_episode_identity_cannot_be_relabelled():
    native = _episode()
    route = route_episode_semantic_lenses(native)
    forged = copy.deepcopy(route)
    forged["routes"][0]["question"] = "Everything is a verified success"
    with pytest.raises(TriangleSemanticError, match="digest"):
        verify_episode_semantic_lenses(native, forged)
    altered = copy.deepcopy(native)
    altered["companion_viewing"]["native_rgb24_frames_optically_inspected"] = 0
    with pytest.raises(TriangleSemanticError, match="source or catalog"):
        verify_episode_semantic_lenses(altered, route)
