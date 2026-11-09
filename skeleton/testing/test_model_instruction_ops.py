import pytest
from skeleton.ai.runtime.deferred.model_instruction_ops import *

D="a"*64
def test_research_evidence_state_is_not_inferred_from_narrative():
 d=ResearchDashboard((ResearchFindingView("f","sounds certain",EvidenceState.UNVERIFIED,"src@1","exp1"),),())
 assert d.verified_count==0
def test_model_promotion_requires_matching_healthy_deployment():
 d=ModelDeployment("dep",D,D,D,"canary")
 assert not decide_promotion(d,ModelHealth("other",True,D)).promote
 assert not decide_promotion(d,ModelHealth("dep",False,D)).promote
 assert decide_promotion(d,ModelHealth("dep",True,D)).promote
def test_deployment_identity_binds_artifact_config_eval():
 a=ModelDeployment("dep",D,D,D,"canary"); b=ModelDeployment("dep","b"*64,D,D,"canary")
 assert a.identity!=b.identity
def test_rollback_requires_prior_version_and_state_reconciliation():
 a=ModelVersionFence("new",D,D); old=ModelVersionFence("old","b"*64,D)
 with pytest.raises(ValueError,match="session"): ModelRollbackPlan(a,old,False,True)
 with pytest.raises(ValueError,match="prior"): ModelRollbackPlan(a,a,True,True)
 assert ModelRollbackPlan(a,old,True,True).target==old
def test_instruction_registry_rejects_authority_smuggling():
 with pytest.raises(ValueError,match="cannot grant authority"): InstructionBinding("a","v",D,"chat",("admin",))
def test_instruction_binding_is_model_and_capability_specific():
 v=InstructionVersion("v1",D,D,"chat",D); a=InstructionAsset("prompt",(v,))
 assert bind_instruction(a,"v1",D,"chat").version_id=="v1"
 with pytest.raises(PermissionError): bind_instruction(a,"v1","b"*64,"chat")
def test_prompt_regression_fails_if_pinned_context_changes():
 b=PromptBaseline(D,D,D,1,1,1,0.1); t=PromptTest("t",b,.1,.1,.1,.1)
 c=PromptBaseline("b"*64,D,D,1,1,1,0.1)
 assert evaluate_prompt(t,c).reasons==("execution context changed",)
def test_prompt_regression_tracks_quality_safety_cost_and_nondeterminism():
 b=PromptBaseline(D,D,D,1,1,1,.1); t=PromptTest("t",b,.05,.05,.1,.05)
 c=PromptBaseline(D,D,D,.8,.8,1.5,.3)
 r=evaluate_prompt(t,c)
 assert not r.passed
 assert set(r.reasons)=={"quality regression","safety regression","cost regression","nondeterminism regression"}
