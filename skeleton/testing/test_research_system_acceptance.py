from __future__ import annotations
import hashlib,pytest
from skeleton.eval.research_acceptance import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def coverage(**kw):
 v=dict(claim_id="CLAIM.1",evidence_digests=(S("support"),),contradiction_digests=(S("conflict"),),uncertainty_recorded=True,negative_results_preserved=True);v.update(kw);return ClaimEvidenceCoverage(**v)
def repro(ok=True):return ReproductionEvidence("REPRO.1","CLAIM.1",S("method"),S("result"),"ACTOR.REPRO","ACTOR.RESEARCH",ok)
def acceptance(**kw):
 v=dict(acceptance_id="ACCEPT.106",conclusion_digest=S("conclusion"),coverage=(coverage(),),reproductions=(repro(),),high_impact=True,reviewer_id="ACTOR.REVIEW",researcher_id="ACTOR.RESEARCH");v.update(kw);return ResearchAcceptance(**v)
def test_complete_independently_reproduced_research_is_eligible():assert acceptance().eligible
def test_uncertainty_omission_blocks_acceptance():assert not acceptance(coverage=(coverage(uncertainty_recorded=False),)).eligible
def test_negative_result_omission_blocks_acceptance():assert not acceptance(coverage=(coverage(negative_results_preserved=False),)).eligible
def test_failed_reproduction_blocks_acceptance():assert not acceptance(reproductions=(repro(False),)).eligible
def test_high_impact_self_review_rejected():
 with pytest.raises(ResearchAcceptanceError,match="independent review"):acceptance(reviewer_id="ACTOR.RESEARCH")
def test_self_reproduction_rejected():
 with pytest.raises(ResearchAcceptanceError,match="independent"):ReproductionEvidence("REPRO.1","CLAIM.1",S("m"),S("r"),"ACTOR.X","ACTOR.X",True)
def test_claim_without_supporting_evidence_rejected():
 with pytest.raises(ResearchAcceptanceError,match="supporting"):coverage(evidence_digests=())
