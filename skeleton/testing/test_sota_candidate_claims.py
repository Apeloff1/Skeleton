from __future__ import annotations
import hashlib,pytest
from skeleton.eval.sota_qualification import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def claim():return SOTACandidateClaim("CLAIM.SOTA",S("candidate"),"BENCH.1","code-generation","held-out-population","METRIC.PASSRATE","ACTOR.RESEARCH")
def comparison(**kw):
 v=dict(claim_digest=claim().digest,baseline_id="BASELINE.1",baseline_digest=S("baseline"),candidate_score=.9,baseline_score=.8,effect_size=.1,confidence_low=.02,contamination_checked=True);v.update(kw);return BaselineComparison(**v)
def evidence(**kw):
 v=dict(claim_digest=claim().digest,comparison=comparison(),replay_digest=S("replay"),replayer_id="ACTOR.REPLAY",researcher_id="ACTOR.RESEARCH",robustness_digest=S("robust"),security_digest=S("security"),latency_digest=S("latency"),cost_digest=S("cost"),operations_digest=S("ops"));v.update(kw);return QualificationEvidence(**v)
def test_supported_independent_claim_qualifies():assert evidence().qualified
def test_contamination_unchecked_cannot_qualify():assert not evidence(comparison=comparison(contamination_checked=False)).qualified
def test_weak_baseline_result_cannot_qualify():assert not evidence(comparison=comparison(candidate_score=.7)).qualified
def test_statistically_unsupported_effect_cannot_qualify():assert not evidence(comparison=comparison(confidence_low=-.01)).qualified
def test_self_replay_rejected():
 with pytest.raises(QualificationError,match="independent"):evidence(replayer_id="ACTOR.RESEARCH")
def test_comparison_must_bind_exact_claim():
 bad=comparison(claim_digest=S("other"))
 with pytest.raises(QualificationError,match="wrong claim"):evidence(comparison=bad)
def test_claim_requires_exact_task_and_population_scope():
 with pytest.raises(QualificationError,match="scope"):SOTACandidateClaim("CLAIM.X",S("c"),"BENCH.X","","population","METRIC.X","ACTOR.X")

def test_comparison_statistics_reject_nan_and_boolean_aliases():
 with pytest.raises(QualificationError,match="finite numeric"):comparison(candidate_score=float("nan"))
 with pytest.raises(QualificationError,match="finite numeric"):comparison(effect_size=True)
 with pytest.raises(QualificationError,match="contamination_checked must be bool"):comparison(contamination_checked=1)
def test_qualification_receipt_binds_exact_claim_and_evidence():
 c=claim();e=evidence();r=qualify(c,e);verify_qualification(c,e,r)
 other=SOTACandidateClaim("CLAIM.OTHER",S("other"),"BENCH.1","code-generation","held-out-population","METRIC.PASSRATE","ACTOR.RESEARCH")
 with pytest.raises(QualificationError,match="identity mismatch"):qualify(other,e)
def test_qualification_receipt_tampering_is_detected():
 from dataclasses import replace
 c=claim();e=evidence();r=qualify(c,e)
 with pytest.raises(QualificationError,match="drift or tampering"):verify_qualification(c,e,replace(r,evidence_digest=S("forged")))
