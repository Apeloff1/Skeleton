from skeleton.ai.runtime.deferred.claim_governance import *
S=ClaimScope((ScopeDimension("region","NO"),),0,10)
def test_diversity_accounts_for_lineage_owner_citation_and_quality_floor():
 a=EvidenceIndependence("a","wire","owner",frozenset({"root"}),.9);b=EvidenceIndependence("b","wire","owner",frozenset({"root"}),.9)
 d=diversity((a,b),.8);assert d.independent_clusters==1 and d.admissible
 assert not diversity((a,EvidenceIndependence("c","x","y",frozenset(),.1)),.8).admissible
def test_scope_is_first_class_and_time_sensitive():
 assert scope_compatibility(S,ClaimScope((ScopeDimension("region","NO"),),5,20)).compatible
 assert not scope_compatibility(S,ClaimScope((ScopeDimension("region","SE"),),5,20)).compatible
 assert not scope_compatibility(S,ClaimScope((ScopeDimension("region","NO"),),11,20)).compatible
def test_dedup_keeps_lineage_and_rejects_different_scope():
 f=ClaimFingerprint("claim",S);m=merge_claims((("a",f),("b",f)));assert m.lineage==("a","b")
 try:merge_claims((("a",f),("b",ClaimFingerprint("claim",ClaimScope((ScopeDimension("region","SE"),),0,10)))));assert False
 except ValueError:pass
def test_expiration_marks_stale_without_erasing_lineage():
 p=ExpirationPolicy(100,10);assert claim_validity(0,11,p,True) is ClaimValidity.STALE
 r=RevalidationRequest("c",("e1","e2"));assert r.prior_evidence==("e1","e2")
def test_reconciliation_preserves_unresolved_conflict_and_evidence():
 c=ReconciliationCase("x",KnowledgeConflict(("a","b"),("e1","e2")))
 d=reconcile(c);assert d.resolved_claim_id is None and d.competing_evidence==("e1","e2")
 try:reconcile(c,"a",None);assert False
 except ValueError:pass
def test_snapshot_binds_watermarks_model_schema_and_cannot_override_new_source():
 s=KnowledgeSnapshot("src1","idx1","m1","schema1");assert s.digest
 assert restore_allowed(s,"src1") and not restore_allowed(s,"src2")


def test_claim_governance_invalid_inputs_fail_closed():
 import pytest
 with pytest.raises(ValueError): ExpirationPolicy(-1,1)
 with pytest.raises(ValueError): claim_validity(10,9,ExpirationPolicy(5,1),False)
 duplicate=ReconciliationCase("case",KnowledgeConflict(("a","a"),("e",)))
 with pytest.raises(ValueError): reconcile(duplicate)
 incomplete=ReconciliationCase("case",KnowledgeConflict(("a","b"),()))
 with pytest.raises(ValueError): reconcile(incomplete)
 valid=ReconciliationCase("case",KnowledgeConflict(("a","b"),("e",)))
 with pytest.raises(ValueError): reconcile(valid,None,"prefer-current")
 with pytest.raises(ValueError): KnowledgeSnapshot("source","","model","schema")
