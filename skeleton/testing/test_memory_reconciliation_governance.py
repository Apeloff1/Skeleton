import hashlib
import pytest
from skeleton.memory.reconciliation import MemoryAction, MemoryConflictCandidate, MemoryConflictResolver
from skeleton.memory.reconciliation_governance import ReconciliationGovernanceError, authorize_supersession, issue_reconciliation_receipt

def c(i,confidence,prov,digest):
    return MemoryConflictCandidate(record_id=i,scope_key="tenant:n",claim_key="k",payload_digest=hashlib.sha256(digest.encode()).hexdigest(),confidence=confidence,provenance_count=prov,updated_at=1.0)

def conflict():
    return MemoryConflictResolver().build((c("a",.95,4,"a"),c("b",.40,1,"b")),created_at=1.0)

def test_receipt_is_deterministic_and_evidence_bound():
    r=MemoryConflictResolver(); x=conflict()
    args=dict(resolver=r,quality_actions={"a":MemoryAction.RETAIN,"b":MemoryAction.TOMBSTONE},evidence_refs=("eval:2","eval:1","eval:1"))
    a,ra=issue_reconciliation_receipt(x,**args); b,rb=issue_reconciliation_receipt(x,**args)
    assert a==b and ra==rb and ra.evidence_refs==("eval:1","eval:2")
    assert authorize_supersession(a,ra)==("a",("b",))

def test_ambiguous_conflict_fails_closed():
    r=MemoryConflictResolver(); x=r.build((c("a",.6,1,"a"),c("b",.6,1,"b")),created_at=1.0)
    with pytest.raises(ReconciliationGovernanceError,match="ambiguous"):
        issue_reconciliation_receipt(x,resolver=r,quality_actions={},evidence_refs=("eval:1",))

def test_missing_evidence_fails_closed():
    with pytest.raises(ReconciliationGovernanceError,match="evidence"):
        issue_reconciliation_receipt(conflict(),resolver=MemoryConflictResolver(),quality_actions={"a":MemoryAction.RETAIN,"b":MemoryAction.TOMBSTONE},evidence_refs=())

def test_receipt_cannot_authorize_different_conflict():
    r=MemoryConflictResolver(); a,receipt=issue_reconciliation_receipt(conflict(),resolver=r,quality_actions={"a":MemoryAction.RETAIN,"b":MemoryAction.TOMBSTONE},evidence_refs=("eval:1",))
    other=r.build((c("c",.95,4,"c"),c("d",.4,1,"d")),created_at=1.0)
    other=r.resolve(other,quality_actions={"c":MemoryAction.RETAIN,"d":MemoryAction.TOMBSTONE})
    with pytest.raises(ReconciliationGovernanceError,match="bind"):
        authorize_supersession(other,receipt)
