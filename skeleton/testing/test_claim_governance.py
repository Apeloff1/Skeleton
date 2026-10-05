from skeleton.ai.runtime.deferred.claim_governance import *
S=ClaimScope((ScopeDimension("region","NO"),),0,10)
def test_diversity_accounts_for_lineage_owner_citation_and_quality_floor():
 a=EvidenceIndependence("a","wire","owner",frozenset({"root"}),.9);b=EvidenceIndependence("b","wire","owner",frozenset({"root"}),.9)
 assert diversity((a,b),.8).independent_clusters==1 and diversity((a,b),.8).admissible
 assert not diversity((a,EvidenceIndependence("c","x","y",frozenset(),.1)),.8).admissible
def test_scope_is_first_class_and_time_sensitive():
 assert scope_compatibility(S,ClaimScope((ScopeDimension("region","NO"),),5,20)).compatible
 assert not scope_compatibility(S,ClaimScope((ScopeDimension("region","SE"),),5,20)).compatible
 assert not scope_compatibility(S,ClaimScope((ScopeDimension("region","NO"),),11,20)).compatible
def test_dedup_keeps_lineage_and_rejects_different_scope():
 f=ClaimFingerprint("claim",S);assert merge_claims((( "a",f),( "b",f))).lineage==("a","b")
 try: merge_claims((( "a",f),( "b",ClaimFingerprint("claim",ClaimScope((ScopeDimension("region","SE"),),0,10)))))
 except ValueError: pass
 else: assert False
def test_expiration_marks_stale_without_erasing_lineage():
 p=ExpirationPolicy(100,10);assert claim_validity(0,11,p,True) is ClaimValidity.STALE
 assert RevalidationRequest("c",("e1","e2")).prior_evidence==("e1","e2")
def test_reconciliation_preserves_unresolved_conflict_and_evidence():
 c=ReconciliationCase("x",KnowledgeConflict(("a","b"),("e1","e2")));d=reconcile(c)
 assert d.resolved_claim_id is None and d.competing_evidence==("e1","e2")
 try: reconcile(c,"a",None)
 except ValueError: pass
 else: assert False
def test_snapshot_binds_watermarks_model_schema_and_cannot_override_new_source():
 s=KnowledgeSnapshot("src1","idx1","m1","schema1");assert s.digest
 assert restore_allowed(s,"src1") and not restore_allowed(s,"src2")


def test_claim_governance_depth_invariants_fail_closed():
 import pytest
 e=EvidenceIndependence("s","l","o",frozenset(),0.5)
 with pytest.raises(ValueError): diversity((e,),1.1)
 with pytest.raises(ValueError): diversity((e,e),0.1)
 with pytest.raises(ValueError): diversity((EvidenceIndependence("s","l","o",frozenset(),1.1),),0.1)
 with pytest.raises(ValueError): ClaimScope((ScopeDimension("region","NO"),ScopeDimension("region","SE")),0,None)
 with pytest.raises(ValueError): ClaimScope((ScopeDimension("region","NO"),),10,9)
 scope=ClaimScope((ScopeDimension("region","NO"),),0,None)
 fp=ClaimFingerprint("claim",scope)
 with pytest.raises(ValueError): merge_claims((("c",fp),("c",fp)))
 snap=KnowledgeSnapshot("src","idx","model","schema")
 assert restore_allowed(snap,"src","idx","model","schema")
 assert not restore_allowed(snap,"src","other","model","schema")
 assert not restore_allowed(snap,"src","idx","other","schema")
 assert not restore_allowed(snap,"src","idx","model","other")
