import pytest
from skeleton.ai.runtime.deferred.epistemic_integrity import *
D="a"*64
def claim(cid,val,start=0,end=None,recorded=1):
 return TemporalClaim(cid,"s","p",val,ValidityInterval(start,end),recorded,D)
def test_temporal_correction_preserves_history_and_supersedes_current_view():
 k=TemporalKnowledge(); k.append(KnowledgeRevision("r1",claim("c1","old"),None)); k.append(KnowledgeRevision("r2",claim("c2","new",recorded=2),"r1"))
 assert len(k.history)==2
 assert [r.claim.value for r in k.as_of(2,3)]==["new"]
 assert [r.claim.value for r in k.as_of(1,3)]==["old"]
def test_temporal_validity_prevents_stale_fact_from_current_query():
 k=TemporalKnowledge(); k.append(KnowledgeRevision("r",claim("c","expired",0,5),None))
 assert k.as_of(10,6)==()
def test_temporal_rejects_dangling_correction():
 with pytest.raises(ValueError,match="missing"): TemporalKnowledge().append(KnowledgeRevision("r2",claim("c","x"),"r1"))
def test_competing_hypotheses_remain_independent_until_evidence_resolves():
 e=HypothesisEngine((Hypothesis("h1","A",.5),Hypothesis("h2","B",.5)))
 e.add_evidence(HypothesisEvidence("e1","h1",EvidenceDirection.SUPPORTS,D,"test"))
 assert e.resolve("h1") is HypothesisStatus.SUPPORTED
 assert e.resolve("h2") is HypothesisStatus.OPEN
def test_contradictory_evidence_falsifies_instead_of_being_discarded():
 e=HypothesisEngine((Hypothesis("h","A",.9),))
 e.add_evidence(HypothesisEvidence("e1","h",EvidenceDirection.SUPPORTS,D,"test"))
 e.add_evidence(HypothesisEvidence("e2","h",EvidenceDirection.CONTRADICTS,D,"test"))
 assert e.resolve("h") is HypothesisStatus.FALSIFIED
 assert len(e.evidence)==2
def test_plausibility_is_not_verified_fact():
 h=Hypothesis("h","likely",.99)
 assert h.status is HypothesisStatus.OPEN
def test_causal_claim_requires_assumptions_and_evidence():
 with pytest.raises(ValueError,match="assumptions"): CausalClaim("c","x","y",CausalMethod.OBSERVATIONAL,D,())
 c=CausalClaim("c","x","y",CausalMethod.RANDOMIZED,D,("randomization valid",))
 assert c.evidence_digest==D
def test_simulation_cannot_be_reported_as_observed_intervention():
 with pytest.raises(ValueError,match="cannot be labeled observed"): InterventionResult("i","c",CausalMethod.SIMULATED,True,D)
def test_causal_graph_rejects_duplicate_claim_identity():
 c=CausalClaim("c","x","y",CausalMethod.OBSERVATIONAL,D,("no unmeasured confounding",))
 with pytest.raises(ValueError,match="unique"): CausalGraph((c,c))
