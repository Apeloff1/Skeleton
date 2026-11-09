from skeleton.ai.runtime.deferred.lifecycle_governance import *
def test_unknown_or_conflicting_license_blocks_distribution():
 assert not license_compatibility((LicenseRecord("a","1",None,"p",()),),True).compatible
 r=LicenseRecord("a","1","X","p",(LicenseObligation("no-redistribution",True),))
 assert not license_compatibility((r,),True).compatible
def test_data_rights_enforce_consent_purpose_geography_and_use():
 g=UsageGrant("eval",frozenset({"NO"}),30,False,True)
 assert rights_decision(DataRights("d",(g,),True),"eval","NO",evaluation=True).allowed
 assert not rights_decision(DataRights("d",(g,),True),"train","NO",training=True).allowed
def test_sensitive_research_needs_consent_and_oversight_not_tests():
 r=EthicsReview("e",ResearchRisk(True,False,False),True,None);assert not ethics_decision(r).approved
 assert ethics_decision(EthicsReview("e",r.risk,True,"oversight")).approved
def test_model_transition_requires_owner_evidence_rollback_retention():
 m=ModelLifecycle("m",ModelState.INTAKE)
 try:transition_model(m,ModelTransition(ModelState.INTAKE,ModelState.EVALUATED,ModelGovernanceEvidence("e","o","","r")));assert False
 except ValueError:pass
 assert transition_model(m,ModelTransition(ModelState.INTAKE,ModelState.EVALUATED,ModelGovernanceEvidence("e","o","rb","r"))).state is ModelState.EVALUATED
def test_model_retirement_waits_for_consumers_or_explicit_exception():
 d=ModelDeprecation("m","m2",10,(ModelConsumer("c",False),))
 assert not retire_model(d).allowed and retire_model(d,"exception").allowed
def test_provider_cutover_requires_full_parity_shadow_and_rollback():
 p=ProviderParity(True,True,True,True,True)
 assert provider_cutover(ProviderMigration("a","b",p,True,True)).allowed
 assert not provider_cutover(ProviderMigration("a","b",p,True,False)).allowed
def test_experiment_cannot_make_production_claim():
 e=ExperimentExposure(ExperimentalFeature("x",True,True),True,ExperimentKillSwitch(True))
 assert not experiment_allowed(e)
def test_research_merge_cannot_bypass_production_gates():
 p=ResearchBranchPolicy(frozenset({"alice"}));b=ResearchBranch("r","main","alice")
 assert not research_merge(ResearchMergeCandidate(b,True,False),p)
def test_technique_retirement_preserves_reason_replacement_archive():
 r=TechniqueRetirement(Technique("t","1"),RetirementEvidence("obsolete","t2",("c",),"archive/t/1"))
 assert retirement_complete(r)


def test_lifecycle_governance_invalid_inputs_fail_closed():
 import pytest
 rights=DataRights("d",(UsageGrant("research",frozenset({"NO"}),-1,False,True),),True)
 assert not rights_decision(rights,"research","NO",evaluation=True).allowed
 assert not ethics_decision(EthicsReview("",ResearchRisk(False,False,False),True,None)).approved
 ev=ModelGovernanceEvidence("e","owner","rollback","retain")
 with pytest.raises(ValueError): transition_model(ModelLifecycle("m",ModelState.INTAKE),ModelTransition(ModelState.INTAKE,ModelState.DEPLOYED,ev))
 with pytest.raises(ValueError): retire_model(ModelDeprecation("m","replacement",-1,()))
 parity=ProviderParity(True,True,True,True,True)
 assert not provider_cutover(ProviderMigration("p","p",parity,True,True)).allowed
 assert not experiment_allowed(ExperimentExposure(ExperimentalFeature("",True),True,ExperimentKillSwitch(True)))
 policy=ResearchBranchPolicy(frozenset({"owner"}))
 assert not research_merge(ResearchMergeCandidate(ResearchBranch("","main","owner"),True,True),policy)
 evidence=RetirementEvidence("reason","replacement",("",),"archive")
 assert not retirement_complete(TechniqueRetirement(Technique("t","v1"),evidence))
