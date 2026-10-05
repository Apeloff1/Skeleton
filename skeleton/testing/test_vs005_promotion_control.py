from __future__ import annotations
import hashlib,pytest
from skeleton.learning.promotion_control import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def candidate():return ImprovementCandidate("CANDIDATE.101",S("champion"),S("challenger"),"isolated:forge",("METRIC.QUALITY",),"ACTOR.BUILDER")
def evaluation(**kw):
 v=dict(candidate_digest=candidate().digest,metric_values=(("METRIC.QUALITY",.9),),safety_passed=True,cost_passed=True,robustness_passed=True,evidence_digest=S("eval"));v.update(kw);return EvaluationBundle(**v)
def test_candidate_requires_distinct_challenger():
 with pytest.raises(ImprovementError,match="differ"):ImprovementCandidate("CANDIDATE.X",S("same"),S("same"),"scope",("METRIC.X",),"ACTOR.B")
def test_self_promotion_rejected():
 with pytest.raises(ImprovementError,match="independent"):decide(candidate(),evaluation(),"ACTOR.BUILDER",canary_digest=S("canary"))
def test_metric_substitution_rejected():
 e=evaluation(metric_values=(("METRIC.OTHER",1.0),))
 with pytest.raises(ImprovementError,match="preregistration"):decide(candidate(),e,"ACTOR.VERIFIER",canary_digest=S("canary"))
def test_failed_safety_rejects_even_with_quality_score():
 d=decide(candidate(),evaluation(safety_passed=False),"ACTOR.VERIFIER",canary_digest=None);assert d.status is PromotionStatus.REJECT
def test_failed_cost_rejects():
 assert decide(candidate(),evaluation(cost_passed=False),"ACTOR.VERIFIER",canary_digest=None).status is PromotionStatus.REJECT
def test_failed_robustness_rejects():
 assert decide(candidate(),evaluation(robustness_passed=False),"ACTOR.VERIFIER",canary_digest=None).status is PromotionStatus.REJECT
def test_promotion_requires_canary():
 with pytest.raises(ImprovementError,match="canary"):decide(candidate(),evaluation(),"ACTOR.VERIFIER",canary_digest=None)
def test_valid_independent_promotion_binds_canary():
 d=decide(candidate(),evaluation(),"ACTOR.VERIFIER",canary_digest=S("canary"));assert d.status is PromotionStatus.PROMOTE and d.canary_digest==S("canary")
def test_rollback_receipt_restores_distinct_champion():
 r=RollbackReceipt("DECISION.CANDIDATE.101",S("challenger"),S("champion"),S("rollback"));assert r.restored_digest==S("champion")
