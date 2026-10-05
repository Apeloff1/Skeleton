from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.research_evaluation_review import ResearchEvaluationReviewError,build_research_evaluation_review

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def evidence():
    return {name:d(name) for name in (
        "research_agent_team","literature_watch","citation_graph","reproduction_package",
        "experiment_comparison","statistical_analysis","model_eval","agent_eval",
        "long_horizon","contamination_audit","human_evaluation",
    )}

def test_review_binds_all_eleven_volume_surfaces_to_one_revision():
    review=build_research_evaluation_review(
        review_id="r",source_revision="a"*40,subject_id="research-stack",
        evidence_digests=evidence(),blockers=(),
        independent_verifier_id="verifier",producer_id="producer",
    )
    assert review.status=="ready_for_independent_closure"
    assert review.promotion_authority is False
    assert len(review.evidence_digests)==11
    assert len(review.digest)==64

def test_missing_volume_evidence_fails_closed():
    data=evidence(); data.pop("human_evaluation")
    with pytest.raises(ResearchEvaluationReviewError,match="exact VOL-210..220"):
        build_research_evaluation_review(
            review_id="r",source_revision="b"*40,subject_id="s",
            evidence_digests=data,blockers=(),independent_verifier_id="v",producer_id="p",
        )

def test_verifier_must_be_independent():
    with pytest.raises(ResearchEvaluationReviewError,match="independent"):
        build_research_evaluation_review(
            review_id="r",source_revision="c"*40,subject_id="s",
            evidence_digests=evidence(),blockers=(),independent_verifier_id="same",producer_id="same",
        )

def test_blockers_surface_explicitly():
    review=build_research_evaluation_review(
        review_id="r",source_revision="d"*40,subject_id="s",
        evidence_digests=evidence(),blockers=("contamination_detected",),
        independent_verifier_id="v",producer_id="p",
    )
    assert review.status=="blocked"
    assert review.blockers==("contamination_detected",)
