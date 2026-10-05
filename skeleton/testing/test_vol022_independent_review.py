import pytest
from skeleton.automation.transactional_workspace import TransactionalWorkspace, WorkspaceError
from skeleton.automation.independent_review import ReviewFinding, ReviewReceipt, review_workspace, verify_review

D="0"*64
def proposal(content=b"x"):
    w=TransactionalWorkspace({"a":b"old"}); import hashlib
    w.write("a",content,expected_digest=hashlib.sha256(b"old").hexdigest()); return w.commit()

def test_independent_approval_binds_exact_workspace():
    p=proposal(); r=review_workspace(p,proposer_id="builder",reviewer_id="verifier",decision="approve")
    assert verify_review(p,r) and r.authority_scope=="review-evidence-only"

def test_same_actor_cannot_self_review():
    with pytest.raises(WorkspaceError): review_workspace(proposal(),proposer_id="builder",reviewer_id="builder",decision="approve")

def test_blocking_finding_cannot_be_approved():
    f=ReviewFinding("TEST-FAIL",D,True)
    with pytest.raises(WorkspaceError): review_workspace(proposal(),proposer_id="builder",reviewer_id="verifier",decision="approve",findings=[f])

def test_rejection_preserves_blocking_evidence():
    f=ReviewFinding("TEST-FAIL",D,True); r=review_workspace(proposal(),proposer_id="builder",reviewer_id="verifier",decision="reject",findings=[f])
    assert r.decision=="reject" and r.findings==(f,)

def test_review_cannot_be_replayed_for_other_proposal():
    a=proposal(b"a"); b=proposal(b"b")
    r=review_workspace(a,proposer_id="builder",reviewer_id="verifier",decision="approve")
    assert not verify_review(b,r)

def test_review_identity_is_deterministic():
    p=proposal(); a=review_workspace(p,proposer_id="builder",reviewer_id="verifier",decision="approve"); b=review_workspace(p,proposer_id="builder",reviewer_id="verifier",decision="approve")
    assert a.review_digest==b.review_digest

def test_authority_escalation_rejected():
    p=proposal()
    with pytest.raises(WorkspaceError): ReviewReceipt(p.result_digest,p.operation_digest,"builder","verifier","approve",(),"execution")

def test_rejected_review_never_verifies_as_approval():
    p=proposal()
    r=review_workspace(p,proposer_id="builder",reviewer_id="verifier",decision="reject")
    assert not verify_review(p,r)

def test_rejection_with_blocking_finding_never_verifies():
    p=proposal(); f=ReviewFinding("TEST-FAIL",D,True)
    r=review_workspace(p,proposer_id="builder",reviewer_id="verifier",decision="reject",findings=[f])
    assert not verify_review(p,r)
