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

def test_evaluation_rejects_duplicate_nonfinite_and_boolean_metrics():
 with pytest.raises(ImprovementError,match="duplicate"):evaluation(metric_values=(("METRIC.QUALITY",.9),("METRIC.QUALITY",.8)))
 with pytest.raises(ImprovementError,match="finite numeric"):evaluation(metric_values=(("METRIC.QUALITY",float("nan")),))
 with pytest.raises(ImprovementError,match="finite numeric"):evaluation(metric_values=(("METRIC.QUALITY",True),))
def test_promotion_gates_are_strict_booleans():
 with pytest.raises(ImprovementError,match="safety_passed must be bool"):evaluation(safety_passed=1)
 with pytest.raises(ImprovementError,match="cost_passed must be bool"):evaluation(cost_passed="yes")
def test_metric_preregistration_collection_is_bounded_tuple():
 c=candidate()
 with pytest.raises(ImprovementError,match="bounded tuple"):ImprovementCandidate("CANDIDATE.X",c.champion_digest,c.challenger_digest,"scope",["METRIC.X"],"ACTOR.B")
def test_rollback_must_restore_exact_champion_for_exact_promotion():
 c=candidate();d=decide(c,evaluation(),"ACTOR.VERIFIER",canary_digest=S("canary"))
 good=RollbackReceipt(d.decision_id,c.challenger_digest,c.champion_digest,S("rollback"));validate_rollback(c,d,good)
 wrong=RollbackReceipt(d.decision_id,c.challenger_digest,S("other"),S("rollback"))
 with pytest.raises(ImprovementError,match="exact champion"):validate_rollback(c,d,wrong)
def test_rejected_candidate_cannot_claim_promotion_rollback():
 c=candidate();d=decide(c,evaluation(safety_passed=False),"ACTOR.VERIFIER",canary_digest=None)
 r=RollbackReceipt(d.decision_id,c.challenger_digest,c.champion_digest,S("rollback"))
 with pytest.raises(ImprovementError,match="promoted candidate"):validate_rollback(c,d,r)

def test_outcome_bound_canary_must_match_candidate_and_pass_all_gates():
 c=candidate();e=evaluation();good=CanaryEvidence(c.digest,S("run"),True,True,True)
 d=promote_with_canary(c,e,"ACTOR.VERIFIER",good);assert d.canary_digest==good.digest
 other=CanaryEvidence(S("other"),S("run"),True,True,True)
 with pytest.raises(ImprovementError,match="canary/candidate"):promote_with_canary(c,e,"ACTOR.VERIFIER",other)
 failed=CanaryEvidence(c.digest,S("run"),True,False,True)
 with pytest.raises(ImprovementError,match="canary gates"):promote_with_canary(c,e,"ACTOR.VERIFIER",failed)
