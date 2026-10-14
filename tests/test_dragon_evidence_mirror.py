"""Adversarial controls for three-hatchling disagreement and holdout gating."""
import pytest

from skeleton.ai.game_builder.dragon_evidence_disagreement import (
    three_way_evidence_risks,
)
from skeleton.ai.game_builder.dragon_research_mirror import (
    DragonEvidenceMirror, HoldoutCase,
)


def case(case_id, article, video, update, truth, term):
    return HoldoutCase(case_id, article, video, update,
                       (term,), truth, "b"*64)


def test_polarity_disagreement_is_only_a_review_risk_not_agreement():
    report=three_way_evidence_risks(
        "Gameboy sprite memory is unsupported on firmware v1.0.",
        "Gameboy sprite memory is supported on firmware v2.0.",
        "Gameboy sprite memory may require a migration in firmware v3.0.",
        ("memory",))
    assert "possible_opposing_term_polarity" in report["possible_conflicts"]
    assert "version_scope_disagreement_possible" in report["possible_conflicts"]
    assert "uncertainty_not_shared_by_all_sources" in report["possible_conflicts"]
    assert "memory" in report["contested_terms"]
    assert report["agreement_verified"] is False
    assert report["independent_source_review_required"] is True
    assert report["training_authorized"] is False
    assert report["lens_digest"]==three_way_evidence_risks(
        "Gameboy sprite memory is unsupported on firmware v1.0.",
        "Gameboy sprite memory is supported on firmware v2.0.",
        "Gameboy sprite memory may require a migration in firmware v3.0.",
        ("memory",))["lens_digest"]


def test_absence_of_keyword_conflict_does_not_certify_truth():
    report=three_way_evidence_risks(
        "Sprite memory is available.",
        "Sprite memory is available.",
        "Sprite memory is available.",
        ("memory",))
    assert not report["agreement_verified"]
    assert not report["model_improvement_proven"]
    assert "duplicate_or_paraphrased_evidence_possible" in report["possible_conflicts"]
    with pytest.raises(ValueError,match="bounded"):
        three_way_evidence_risks("x"*2049,"okay", "okay", ("memory",))
    with pytest.raises(ValueError,match="canonical"):
        three_way_evidence_risks("okay","okay","okay", ("../../../",))


def test_independently_labeled_holdout_scores_gain_without_weight_promotion():
    cases=(
        case("conflict-memory", "Gameboy memory is unsupported.",
             "Gameboy memory is supported.", "Memory changed in revision 2.",
             True,"memory"),
        case("no-conflict-memory", "Gameboy memory is supported.",
             "Gameboy memory is supported.", "Memory remains stable.",
             False,"memory"),
        case("conflict-latency", "Frame latency is unsafe.",
             "Frame latency is stable.", "Latency was changed.",
             True,"latency"),
        case("no-conflict-physics", "Physics collision is stable.",
             "Physics collision is stable.", "Physics collision is fixed.",
             False,"physics"),
    )
    a=DragonEvidenceMirror.evaluate(
        cases,reviewed_holdout=True,independent_reviewer=True)
    b=DragonEvidenceMirror.evaluate(
        cases,reviewed_holdout=True,independent_reviewer=True)
    assert a==b
    assert a["challenge_passed"]
    assert a["candidate_correct"]==4 and a["baseline_correct"]==2
    assert a["measured_accuracy_gain_pp"]==50.0
    assert not a["model_weights_promoted"]
    assert not a["independent_provenance_verified_by_runtime"]
    assert not a["neural_training_authorized"]
    assert a["manual_wiki_hoag_review_required"]


def test_mirror_rejects_unreviewed_imbalanced_or_duplicate_holdouts():
    controls=(
        case("a","Memory supported","Memory unsupported","Memory changed",True,"memory"),
        case("b","Memory stable","Memory stable","Memory stable",False,"memory"),
        case("c","Latency unsafe","Latency stable","Latency changed",True,"latency"),
        case("d","Physics good","Physics good","Physics good",False,"physics"),
    )
    with pytest.raises(PermissionError,match="independently"):
        DragonEvidenceMirror.evaluate(
            controls,reviewed_holdout=False,independent_reviewer=True)
    with pytest.raises(ValueError,match="nonduplicate"):
        DragonEvidenceMirror.evaluate(
            (controls[0],controls[0],controls[1],controls[2]),
            reviewed_holdout=True,independent_reviewer=True)
    with pytest.raises(ValueError,match="both disagreement"):
        DragonEvidenceMirror.evaluate(
            (controls[0],controls[0].__class__(
                "e",controls[0].article,controls[0].video,
                controls[0].update,controls[0].shared_terms,True,"b"*64),
             controls[2],controls[2].__class__(
                "f",controls[2].article,controls[2].video,
                controls[2].update,controls[2].shared_terms,True,"b"*64)),
            reviewed_holdout=True,independent_reviewer=True)


@pytest.mark.parametrize("fields", (
    {"article": ""},
    {"video": "x" * 2049},
    {"update": ""},
    {"shared_terms": ()},
    {"shared_terms": ("memory", "memory")},
    {"shared_terms": ("../secrets",)},
    {"shared_terms": ("a" * 41,)},
))
def test_holdout_requires_bounded_passages_and_canonical_unique_terms(fields):
    kwargs = dict(
        case_id="bounded-source",
        article="Game memory is supported.",
        video="Game memory is unsupported.",
        update="Memory changed in revision 2.",
        shared_terms=("memory",),
        expected_polarity_conflict=True,
        reviewer_evidence_digest="b" * 64,
    )
    kwargs.update(fields)
    with pytest.raises(ValueError, match="bounded"):
        HoldoutCase(**kwargs)
