import pytest
from skeleton.ai.runtime.deferred.repository_governance import *
D="a"*64
def test_archaeology_inference_is_not_authority_without_confirmation():
 a=LegacyArtifact("a","old.py","r1",D); h=IntentHypothesis("h","likely intent",Confidence.HIGH,("a",),False)
 assert ArchaeologyFinding("f",a,(h,)).authoritative_intent==()
def test_confirmed_intent_requires_evidence():
 with pytest.raises(ValueError): IntentHypothesis("h","intent",Confidence.HIGH,(),True)
def test_consolidation_retirement_requires_import_inversion_and_evidence_binding():
 m=CustodyMapping("old","new","legacy","canonical"); e=ConsolidationEvidence("p",D,D,D)
 assert not can_retire_source(ConsolidationPlan("p",(m,),"adapter",False),e)
 assert can_retire_source(ConsolidationPlan("p",(m,),"adapter",True),e)
 assert not can_retire_source(ConsolidationPlan("p",(m,),"adapter",True),ConsolidationEvidence("other",D,D,D))
def test_refactor_preserves_source_and_license_lineage():
 o=CodeOrigin(OriginKind.IMPORTED,"upstream@r1","MIT"); a=CodeArtifact("a",D,o)
 b=CodeArtifact("b","b"*64,CodeOrigin(OriginKind.IMPORTED,"other","MIT"))
 with pytest.raises(ValueError,match="source lineage"): CodeTransformation(a,b,"rename")
def test_license_lineage_cannot_disappear():
 a=CodeArtifact("a",D,CodeOrigin(OriginKind.IMPORTED,"src","MIT")); b=CodeArtifact("b","b"*64,CodeOrigin(OriginKind.IMPORTED,"src","UNKNOWN"))
 with pytest.raises(ValueError,match="license"): CodeTransformation(a,b,"refactor")
def test_intentional_adapter_is_not_auto_removal_candidate():
 f=DuplicationFinding("f",("a","b"),DuplicateKind.ADAPTER,.99,"owners","deps")
 with pytest.raises(ValueError,match="intentional"): ConvergenceProposal(f,("b",))
def test_accidental_duplicate_removal_requires_ownership_and_dependencies():
 f=DuplicationFinding("f",("a","b"),DuplicateKind.ACCIDENTAL,.99,None,None)
 with pytest.raises(ValueError,match="ownership"): ConvergenceProposal(f,("b",))
def test_owner_resolution_rejects_orphan_and_overlap():
 z=(OwnershipZone("z1","a",("src/",)),OwnershipZone("z2","b",("src/security/",)))
 with pytest.raises(ValueError): resolve_owner("unknown/x.py",z)
 with pytest.raises(ValueError): resolve_owner("src/security/x.py",z)
def test_owner_resolution_is_deterministic_for_single_zone():
 assert resolve_owner("src/x.py",(OwnershipZone("z","team",("src/",)),)).owner=="team"
def test_ownership_transfer_preserves_history_and_dependency_impact():
 t=OwnershipTransfer("src/x.py","a","b",D,D); assert t.to_owner=="b"
