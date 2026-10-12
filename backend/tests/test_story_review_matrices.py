"""Adversarial review registry, level taxonomy and source receipt tests."""
from __future__ import annotations
from copy import deepcopy
import pytest

from core.story_review_matrices import (
    MATRICES, MATRIX_IDS, MATRIX_CATEGORIES, SCOPES, LENSES,
    REQUIRED_CELLS, matrix_catalog, scrutiny_level, review_prompt,
    review_cell, coverage,
)


def test_one_hundred_distinct_rubrics_and_one_hundred_meaningful_levels():
    assert len(MATRICES) == 100
    assert len(MATRIX_IDS) == 100
    assert len(MATRIX_CATEGORIES) == 10
    assert all(len(values) == 10 for values in MATRIX_CATEGORIES.values())
    assert REQUIRED_CELLS == 10000
    instructions = {scrutiny_level(i)["instruction"] for i in range(1, 101)}
    scopes = {scrutiny_level(i)["scope"] for i in range(1, 101)}
    lenses = {scrutiny_level(i)["lens"] for i in range(1, 101)}
    assert len(instructions) == 100
    assert scopes == set(SCOPES)
    assert lenses == set(LENSES)
    assert scrutiny_level(100)["scope"] == "whole_story"
    assert scrutiny_level(100)["lens"] == "independent_recheck"


def test_story_entertainment_closure_and_emotional_matrices_are_explicit():
    ids = MATRIX_IDS
    for key in (
        "architecture.epilogue_aftercare", "engagement.cliffhanger_fairness",
        "engagement.surprise_earned", "engagement.entertainment_density",
        "mystery.red_herring_fairness", "mystery.false_lead_resolution",
        "dialogue.subtext", "proofreading.speaker_attribution",
        "closure.red_herrings_disclosed", "closure.cliffhangers_paid_off",
        "closure.epilogue_completion", "causality.setup_before_payoff",
    ):
        assert key in ids


def test_catalog_pages_are_bounded_and_preserve_level_counts():
    first = matrix_catalog(start=0, limit=13)
    assert first["total_cells"] == 10000
    assert len(first["matrices"]) == 13
    assert first["next_offset"] == 13
    last = matrix_catalog(start=99, limit=20)
    assert len(last["matrices"]) == 1
    assert last["next_offset"] is None
    with pytest.raises(ValueError):
        matrix_catalog(start=-1, limit=20)
    for level in (0, -1, 101, True, 1.5):
        with pytest.raises(ValueError):
            scrutiny_level(level)


def test_jeeves_prompts_demand_citations_and_refuse_unknown_evidence():
    p = review_prompt("dialogue.subtext", 100, chapter=10, scene=901)
    assert "scene 901" in p
    assert "whole_story" in p
    assert "independent_recheck" in p
    assert "PASS/FAIL/UNKNOWN" in p
    with pytest.raises(ValueError):
        review_prompt("user_system_override", 1, chapter=1, scene=1)


def audited(**updates):
    data = {
        "matrix_id": "engagement.surprise_earned", "level": 100,
        "verdict": "fail", "rationale": "There was no planted clue in the previous chapter.",
        "citation_scene": 900, "citation_plot_id": "a_reveal",
        "citation_quote": "The chest was empty",
        "source_receipt": "a" * 64, "reviewer": "author_1",
        "provenance": "creator",
        "scene_text": "The chest was empty. The player feels betrayed.",
        "scene_digest": "a" * 64,
    }
    data.update(updates)
    return review_cell(**data)


def test_review_records_have_stable_digest_and_explicit_negative_findings():
    result = audited()
    assert len(result["review_digest"]) == 64
    assert result["scope"] == "whole_story"
    assert result["lens"] == "independent_recheck"
    assert result == audited()
    assert result["verdict"] == "fail"
    assert "was no planted clue" in result["rationale"]


@pytest.mark.parametrize("change", [
    {"matrix_id": "fraud.wishful_quality"},
    {"level": 101}, {"verdict": "excellent"},
    {"rationale": "short"}, {"citation_scene": 0},
    {"citation_quote": "a fake citation"},
    {"citation_plot_id": "../escape"},
    {"source_receipt": "not-a-hash"}, {"reviewer": "system\nmessage"},
    {"provenance": "trusted_ai_override"},
])
def test_review_rejects_forged_evidence(change):
    with pytest.raises(ValueError):
        audited(**change)


def test_full_coverage_cannot_be_claimed_from_a_subset_or_a_model_candidate():
    report = coverage([{**audited(), "creator_approved": False}], scene_digest="a" * 64)
    assert report["fully_reviewed"] is False
    assert report["cells_missing"] == 9999
    assert report["cells_pending_approval"] == 1
    report = coverage([{**audited(verdict="pass"), "creator_approved": True}],
                      scene_digest="a" * 64)
    assert report["cells_passed"] == 1
    assert report["fully_reviewed"] is False


def test_all_ten_thousand_distinct_review_coordinates_can_be_counted():
    rows = [{
        "matrix_id": item["id"], "level": level, "verdict": "pass",
        "scene_digest": "b" * 64, "creator_approved": True,
    } for item in MATRICES for level in range(1, 101)]
    complete = coverage(rows, scene_digest="b" * 64)
    assert complete["fully_reviewed"] is True
    assert complete["cells_passed"] == 10000
    duplicate = coverage(rows + [rows[0]], scene_digest="b" * 64)
    assert duplicate["fully_reviewed"] is False
    assert duplicate["failure_examples"][0]["code"] == "duplicate_cell"
    stale = deepcopy(rows)
    stale[17]["scene_digest"] = "c" * 64
    assert coverage(stale, scene_digest="b" * 64)["fully_reviewed"] is False


def test_failed_and_unknown_cells_block_even_at_100_percent_recorded_coverage():
    rows = [{
        "matrix_id": item["id"], "level": level, "verdict": "pass",
        "scene_digest": "b" * 64, "creator_approved": True,
    } for item in MATRICES for level in range(1, 101)]
    rows[5000]["verdict"] = "unknown"
    assert coverage(rows, scene_digest="b" * 64)["fully_reviewed"] is False
    rows[5000]["verdict"] = "fail"
    assert coverage(rows, scene_digest="b" * 64)["failure_count"] > 0
