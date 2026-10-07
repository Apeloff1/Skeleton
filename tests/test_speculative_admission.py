import pytest
from skeleton.ai.speculative_inference import DraftToken,SpeculativePlan,VerificationStep,verify
from skeleton.ai.speculative_admission import SpeculativeAdmission,authorize_speculation,execution_receipt,plan_identity

def adm(**kw):
 d=dict(quality_floor=.95,observed_quality=.98,max_extra_cost=2.,estimated_extra_cost=1.,available_memory_bytes=4096,required_memory_bytes=2048,evaluation_evidence_id="eval:exact-head",budget_evidence_id="budget:op-7",resource_evidence_id="resource:lease-9");d.update(kw);return SpeculativeAdmission(**d)

def test_deterministic_content_bound_identity():
 p=SpeculativePlan("draft-a","target-a",4);assert authorize_speculation(p,adm())==authorize_speculation(p,adm());assert plan_identity(p)!=plan_identity(SpeculativePlan("draft-a","target-a",5))

@pytest.mark.parametrize("change",[{"observed_quality":.94},{"estimated_extra_cost":2.01},{"required_memory_bytes":4097}])
def test_fail_closed_bounds(change):
 with pytest.raises(PermissionError): authorize_speculation(SpeculativePlan("draft-a","target-a",4),adm(**change))

def test_missing_evidence_rejected():
 with pytest.raises(ValueError): adm(evaluation_evidence_id="")

def test_cross_plan_replay_rejected():
 a=SpeculativePlan("draft-a","target-a",4);b=SpeculativePlan("draft-b","target-a",4);auth=authorize_speculation(a,adm())
 with pytest.raises(PermissionError): execution_receipt(b,adm(),auth,())

def test_receipt_binds_rejection_and_fallback():
 p=SpeculativePlan("draft-a","target-a",4);s=verify(p,[DraftToken(1,.9),DraftToken(2,.8)],[1,3]);r=execution_receipt(p,adm(),authorize_speculation(p,adm()),s);assert (r.accepted_tokens,r.rejected_tokens,r.fallback_required)==(1,1,True)

def test_nonterminal_rejection_rejected():
 p=SpeculativePlan("draft-a","target-a",4);s=(VerificationStep(DraftToken(1,.9),9,False),VerificationStep(DraftToken(2,.8),2,True))
 with pytest.raises(ValueError): execution_receipt(p,adm(),authorize_speculation(p,adm()),s)


from skeleton.ai.speculative_admission import ResourceLease,AuthorizationLedger,issue_authorization,validate_live_authorization

def lease(**kw):
 d=dict(lease_id="resource:lease-9",generation=7,issued_at_ns=100,expires_at_ns=200,resource_fingerprint="gpu:abc");d.update(kw);return ResourceLease(**d)

def test_live_authorization_rejects_expired_lease():
 p=SpeculativePlan("draft-a","target-a",4)
 with pytest.raises(PermissionError): issue_authorization(p,adm(),lease(),200)

def test_live_authorization_rejects_preissue_clock():
 p=SpeculativePlan("draft-a","target-a",4)
 with pytest.raises(PermissionError): issue_authorization(p,adm(),lease(),99)

def test_live_authorization_binds_lease_generation_and_resource():
 p=SpeculativePlan("draft-a","target-a",4);a=issue_authorization(p,adm(),lease(),150)
 with pytest.raises(PermissionError): validate_live_authorization(p,adm(),a,lease(generation=8),150)
 with pytest.raises(PermissionError): validate_live_authorization(p,adm(),a,lease(resource_fingerprint="gpu:def"),150)

def test_resource_evidence_must_name_exact_lease():
 p=SpeculativePlan("draft-a","target-a",4)
 with pytest.raises(PermissionError): issue_authorization(p,adm(resource_evidence_id="resource:other"),lease(),150)

def test_authorization_ledger_is_single_use():
 p=SpeculativePlan("draft-a","target-a",4);a=issue_authorization(p,adm(),lease(),150);ledger=AuthorizationLedger();assert ledger.consume(a)==a.authorization_id
 with pytest.raises(PermissionError): ledger.consume(a)
