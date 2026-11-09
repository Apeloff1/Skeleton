"""Independent Dragon evidence-lens regression extracted from draft #3605.

This module deliberately avoids the still-unreconciled holdout mirror.
"""
import pytest

from skeleton.ai.game_builder.dragon_evidence_disagreement import three_way_evidence_risks


def test_polarity_disagreement_is_only_a_review_risk_not_agreement():
    passages = (
        "Gameboy sprite memory is unsupported on firmware v1.0.",
        "Gameboy sprite memory is supported on firmware v2.0.",
        "Gameboy sprite memory may require a migration in firmware v3.0.",
    )
    report = three_way_evidence_risks(*passages, ("memory",))
    assert "possible_opposing_term_polarity" in report["possible_conflicts"]
    assert "version_scope_disagreement_possible" in report["possible_conflicts"]
    assert "uncertainty_not_shared_by_all_sources" in report["possible_conflicts"]
    assert "memory" in report["contested_terms"]
    assert report["agreement_verified"] is False
    assert report["independent_source_review_required"] is True
    assert report["training_authorized"] is False
    assert report["lens_digest"] == three_way_evidence_risks(*passages, ("memory",))["lens_digest"]


def test_no_keyword_conflict_never_certifies_truth():
    report = three_way_evidence_risks(
        "Sprite memory is available.",
        "Sprite memory is available.",
        "Sprite memory is available.",
        ("memory",),
    )
    assert report["agreement_verified"] is False
    assert report["model_improvement_proven"] is False
    assert "duplicate_or_paraphrased_evidence_possible" in report["possible_conflicts"]
    with pytest.raises(ValueError, match="bounded"):
        three_way_evidence_risks("x" * 2049, "okay", "okay", ("memory",))
    with pytest.raises(ValueError, match="canonical"):
        three_way_evidence_risks("okay", "okay", "okay", ("../../../",))
