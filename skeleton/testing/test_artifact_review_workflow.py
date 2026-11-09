import pytest
from skeleton.ai.artifact_review import ArtifactReview, ReviewComment, ReviewDecision, ReviewError, ReviewState

def review():
    return ArtifactReview("artifact:1","sha:a",frozenset({"alice","bob"}),frozenset({"tests","security"}))

def decision(who,digest="sha:a",approved=True):
    return ReviewDecision(who,digest,approved,(f"evidence:{who}",))

def test_promotion_requires_all_reviewers_and_gates():
    r=review(); r.decide(decision("alice")); r.decide(decision("bob")); r.pass_gate("tests","sha:a")
    assert not r.promotable
    r.pass_gate("security","sha:a")
    assert r.promotable

def test_stale_review_decision_fails_closed():
    r=review()
    with pytest.raises(ReviewError,match="stale decision"):
        r.decide(decision("alice","sha:old"))

def test_stale_gate_evidence_fails_closed():
    r=review()
    with pytest.raises(ReviewError,match="stale gate"):
        r.pass_gate("tests","sha:old")

def test_blocking_comment_prevents_approval():
    r=review(); r.comment(ReviewComment("alice","counterexample",("e:1",),True))
    r.decide(decision("alice")); r.decide(decision("bob")); r.pass_gate("tests","sha:a"); r.pass_gate("security","sha:a")
    assert r.state is ReviewState.CHANGES_REQUESTED
    assert not r.promotable

def test_supersede_invalidates_old_approvals_and_gates():
    r=review(); r.decide(decision("alice")); r.pass_gate("tests","sha:a")
    new=r.supersede("sha:b")
    assert r.state is ReviewState.SUPERSEDED
    assert new.decisions=={} and new.passed_gates==set()
    with pytest.raises(ReviewError,match="immutable"):
        r.decide(decision("bob"))

def test_unauthorized_reviewer_cannot_approve():
    r=review()
    with pytest.raises(ReviewError,match="authorized"):
        r.decide(decision("mallory"))
