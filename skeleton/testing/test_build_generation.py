from skeleton.ai.runtime.deferred.build_generation import *
def test_rebuild_requires_verified_inputs_and_exact_evidence():
 assert not rebuild_admissible(RebuildPlan((RebuildStep("a",("x",),"v",False),)))
 assert rebuild_verified(RebuildEvidence("a","d","d",True))
 assert not rebuild_verified(RebuildEvidence("a","d","x",True))
def test_impact_exposes_missing_graph_uncertainty():
 e=ImpactEvidence(True,False,True,("trace:a",));r=impact(ImpactQuery(("a",)),{"a":("b",)},{"b":"team"},e)
 assert r.affected==("a","b") and r.uncertainty==1 and r.evidence.missing_edges
def test_risk_estimator_is_evidence_only_not_a_gate():
 r=estimate_risk((RiskFactor("blast",2,.5),),"cal");assert r.score==1 and not hasattr(r,"admitted")
def test_safe_change_requires_hard_gates_budget_and_reversibility():
 assert not change_admissible(SafeChangePlan((ChangeStep("x",False,None),),(ChangeGate("owner",True),),True))
 assert not change_admissible(SafeChangePlan((ChangeStep("x",True,None),),(ChangeGate("compat",False),),True))
 assert change_admissible(SafeChangePlan((ChangeStep("x",True,None),),(ChangeGate("compat",True),),True))
def test_system_compile_is_deterministic_and_cannot_create_authority():
 s=SystemSource("v1","contract",frozenset({"write"}));p=SystemCompilePlan("g1")
 a=compile_system(s,p);b=compile_system(s,p);assert a==b and not a.authority
def test_generated_code_is_marked_reproducible_and_extensions_external():
 spec=GenerationSpec("v1","g1",(ExtensionPoint("custom","manual/custom.py"),))
 a=generate_code(spec,"x");b=generate_code(spec,"x");assert a==b and "DO NOT EDIT" in a.generated_marker
def test_client_sdk_binds_exact_contract_version_and_digest():
 v=SDKVersion("api-v7","g1");s=generate_client(v,(SDKMethod("get","Req","Res"),),"schema")
 assert s.version.api_contract_version=="api-v7" and s.contract_digest


def test_build_generation_slice_imports_cleanly():
    import skeleton.ai.runtime.deferred.build_generation as module
    assert module.RebuildPlan is not None


def test_rebuild_fail_closed_on_empty_or_unidentified_inputs():
 assert not rebuild_admissible(RebuildPlan(()))
 assert not rebuild_admissible(RebuildPlan((RebuildStep("",("x",),"v",True),)))
 assert not rebuild_admissible(RebuildPlan((RebuildStep("a",(),"v",True),)))
 assert not rebuild_verified(RebuildEvidence("","d","d",True))


def test_impact_and_risk_inputs_fail_closed():
 import pytest
 evidence=ImpactEvidence(True,True,True,())
 with pytest.raises(ValueError): impact(ImpactQuery(()),{}, {}, evidence)
 with pytest.raises(ValueError): estimate_risk((), "cal")
 with pytest.raises(ValueError): estimate_risk((RiskFactor("blast",-1,.5),), "cal")
 with pytest.raises(ValueError): estimate_risk((RiskFactor("blast",1,1.01),), "cal")


def test_change_plan_and_generated_output_identity_hardening():
 assert not change_admissible(SafeChangePlan((),(ChangeGate("owner",True),),True))
 assert not change_admissible(SafeChangePlan((ChangeStep("x",True,None),),(),True))
 assert not change_admissible(SafeChangePlan((ChangeStep("",True,None),),(ChangeGate("owner",True),),True))
 spec=GenerationSpec("v1","g1",(ExtensionPoint("custom","manual/custom.py"),))
 a=generate_code(spec,"x");b=generate_code(spec,"y")
 assert a.spec_digest==b.spec_digest
 assert a.output_digest!=b.output_digest


def test_sdk_generation_rejects_duplicate_method_identity():
 import pytest
 version=SDKVersion("api-v7","g1")
 methods=(SDKMethod("get","Req","Res"),SDKMethod("get","OtherReq","OtherRes"))
 with pytest.raises(ValueError): generate_client(version,methods,"schema")
