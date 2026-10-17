"""Canonical 43-lens routing contracts for verified native triangle evidence.

These tests exercise Jeeves' real maximal registry, routing and governance,
not a mocked 43-item competing registry.
"""
from __future__ import annotations

import pytest

from skeleton.jeeves.game_emulator_triangle_semantics import (
    SEMANTIC_LENS_BUDGET, TriangleSemanticError, route_episode_semantic_lenses,
    verify_episode_semantic_lenses,
)


def _episode():
    # A bounded source-shaped fixture that exercises the REAL Jeeves lens
    # engine, rather than importing a test package from the host environment.
    return {
        "source_trace_sha256": "a" * 64,
        "source_receipt_sha256": "b" * 64,
        "grounded_lens_evidence": {
            "controller_action": {"action_sequence_sha256": "c" * 64},
            "reward_and_consequence": {"measured_reward_sequence_sha256": "d" * 64},
        },
        "companion_viewing": {
            "native_rgb24_frames_optically_inspected": 3,
            "frame_sequence_sha256": "e" * 64,
            "audio_sequence_sha256": "f" * 64,
        },
        "ai_playing": {
            "actual_native_steps": 3,
            "actual_q_table_updates": 3,
            "counterfactual_native_probes": 2,
            "controller_only_probes": 1,
        },
        "repetition": {"replayed_native_steps": 6, "reverse_checkpoint_count": 2},
    }


def test_canonical_43_lenses_are_selected_and_governed():
    episode = _episode()
    result = route_episode_semantic_lenses(episode)
    assert result["actually_routed_lenses"] == SEMANTIC_LENS_BUDGET == 43
    assert result["canonical_catalog_lens_count"] >= 43
    assert len({x["lens_key"] for x in result["routes"]}) == 43
    assert result["source_native_trace_sha256"] == episode["source_trace_sha256"]
    assert result["source_evidence_observation_count"] == 6
    assert result["additional_native_training_examples"] == 0
    assert not result["factual_assertions_authorized"]
    assert not result["causal_assertions_authorized"]
    assert all(x["state"] == "routed_interpretive_question_unanswered"
               and x["new_independent_evidence"] == 0
               and x["training_ground_truth_label_available"] is False
               for x in result["routes"])
    verify_episode_semantic_lenses(episode, result)


def test_operator_manifest_cannot_manufacture_43_full_activation_scores():
    episode = _episode()
    automatically = route_episode_semantic_lenses(episode)
    keys = [x["lens_key"] for x in automatically["routes"]]
    pinned = route_episode_semantic_lenses(episode, requested_keys=keys)
    assert pinned["selection_mode"] == "operator_exact_43"
    assert pinned["actually_routed_lenses"] == 43
    assert pinned["operator_requested_lens_keys"] == keys
    assert pinned["operator_selected_lenses_without_cue_support"] >= 0
    assert all(x["operator_requested_not_evidence"] for x in pinned["routes"])
    # An explicit manifest must not synthesize certainty 1.0 for a lens:
    # it may change which questions run, not their source support.
    assert any(x["activation_score"] < 1.0 for x in pinned["routes"])
    verify_episode_semantic_lenses(episode, pinned)


def test_unknown_duplicate_or_truncated_operator_lens_manifest_fails_closed():
    episode = _episode()
    keys = [x["lens_key"] for x in route_episode_semantic_lenses(episode)["routes"]]
    with pytest.raises(TriangleSemanticError, match="43"):
        route_episode_semantic_lenses(episode, requested_keys=keys[:-1])
    with pytest.raises(TriangleSemanticError, match="43"):
        route_episode_semantic_lenses(episode, requested_keys=keys[:-1] + [keys[0]])
    with pytest.raises(TriangleSemanticError, match="canonical"):
        route_episode_semantic_lenses(episode, requested_keys=keys[:-1] + ["unknown_43_lens"])


def test_edited_semantic_route_fails_against_original_catalog_and_episode():
    episode = _episode()
    original = route_episode_semantic_lenses(episode)
    altered = {**original, "routes": [dict(row) for row in original["routes"]]}
    altered["routes"][0]["question"] = "Invented interpretation must be treated as fact."
    from skeleton.jeeves.game_learning import _digest
    altered["route_digest"] = _digest({
        k: v for k, v in altered.items() if k != "route_digest"
    })
    with pytest.raises(TriangleSemanticError, match="no longer matches"):
        verify_episode_semantic_lenses(episode, altered)


def test_absent_pixel_and_counterfactual_modalities_do_not_activate_semantic_cues():
    from skeleton.jeeves.game_emulator_triangle_semantics import (
        _source_observations,
    )
    episode = _episode()
    episode["companion_viewing"]["native_rgb24_frames_optically_inspected"] = 0
    episode["ai_playing"]["counterfactual_native_probes"] = 0
    obs = _source_observations(episode)
    assert len(obs) == 6
    assert "pixel" not in obs[0].tags
    assert "color" not in obs[0].tags
    assert "music" not in obs[1].tags
    assert "camera" not in obs[0].content.casefold()
    assert "scene" not in obs[0].content.casefold()
    assert "simulation" not in obs[-1].tags
    assert "counterfactual" not in obs[-1].tags
    assert all(item.metadata["semantic_game_footage_interpretation_available"] is False
               for item in obs)
    result = route_episode_semantic_lenses(episode)
    assert result["actually_routed_lenses"] == 43
    assert result["native_rgb24_frames_measured"] == 0
    assert result["native_counterfactual_probes_measured"] == 0
    assert result["unobserved_semantics_cannot_activate_lens_cues"] is True
    assert all(item["semantic_media_interpretation_verified"] is False
               for item in result["routes"])
    assert sum(item["cue_support_present"] for item in result["routes"]) == (
        result["actual_cue_supported_lenses"]
    )
    verify_episode_semantic_lenses(episode, result)


def test_cue_evidence_classes_are_source_bound_and_do_not_create_training_labels():
    episode = _episode()
    route = route_episode_semantic_lenses(episode)
    assert route["native_rgb24_frames_measured"] == 3
    assert set(row["native_evidence_support_class"] for row in route["routes"]) <= {
        "measured_native_cue_present", "hypothesis_only_without_matching_native_cue",
    }
    assert all(row["new_independent_evidence"] == 0
               and row["training_ground_truth_label_available"] is False
               for row in route["routes"])
    verify_episode_semantic_lenses(episode, route)
