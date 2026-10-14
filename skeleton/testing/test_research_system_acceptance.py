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

def test_support_and_contradiction_cannot_share_artifact():
 d=S("same")
 with pytest.raises(ResearchAcceptanceError,match="both support and contradiction"):coverage(evidence_digests=(d,),contradiction_digests=(d,))
def test_coverage_and_reproduction_flags_are_strict_booleans():
 with pytest.raises(ResearchAcceptanceError,match="coverage flags"):coverage(uncertainty_recorded=1)
 with pytest.raises(ResearchAcceptanceError,match="reproduced must be bool"):ReproductionEvidence("REPRO.X","CLAIM.1",S("m"),S("r"),"ACTOR.A","ACTOR.B",1)
def test_uncovered_reproduction_blocks_acceptance():
 extra=ReproductionEvidence("REPRO.2","CLAIM.OTHER",S("m2"),S("r2"),"ACTOR.REPRO","ACTOR.RESEARCH",True)
 assert not acceptance(reproductions=(repro(),extra)).eligible
def test_research_signoff_invalidates_on_evidence_drift():
 a=acceptance();s=sign_acceptance(a);verify_acceptance(a,s)
 changed=acceptance(conclusion_digest=S("changed"))
 with pytest.raises(ResearchAcceptanceError,match="stale or mismatched"):verify_acceptance(changed,s)

def test_lineage_qualification_is_bound_into_acceptance_identity():
 a=acceptance(lineage_qualification_digest=S("lineage-v1"));s=sign_acceptance(a);verify_acceptance(a,s)
 changed=acceptance(lineage_qualification_digest=S("lineage-v2"))
 assert changed.digest!=a.digest
 with pytest.raises(ResearchAcceptanceError,match="stale or mismatched"):verify_acceptance(changed,s)
def test_malformed_lineage_qualification_digest_rejected():
 with pytest.raises(ResearchAcceptanceError,match="lineage_qualification_digest"):acceptance(lineage_qualification_digest="forged")
