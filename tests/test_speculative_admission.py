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
