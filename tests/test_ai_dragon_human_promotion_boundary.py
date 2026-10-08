"""Human-review and final-promotion boundary regressions."""
import sqlite3,pytest
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_adversarial_review_worker import AdversarialReviewOutput
from skeleton.ai.webcrawler.dragon_human_review import DragonHumanReviewLedger
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import NormalizedKnowledge
from skeleton.ai.webcrawler.dragon_memory_promotion_worker import execute_memory_promotion


def setup():
    k=NormalizedKnowledge("c"*64,"h","v1","supported",.95,
      "empirically_calibrated_probability","d"*64,"e"*64,"resolved_support")
    ar=LayerReceipt(AnalysisLayer.ADVERSARIAL_REVIEW,("a"*64,),"b"*64,2,True,False)
    review=AdversarialReviewOutput(ar,(),(k.knowledge_id,))
    ledger=DragonHumanReviewLedger(sqlite3.connect(":memory:"))
    decision,hr=ledger.review("u",review,reviewer_id="human-1",approved=True,
      reviewed_at=10,rationale="evidence reviewed",authorized=True)
    dispatch=LayerDispatch(AnalysisLayer.MEMORY_PROMOTION,(hr.output_fingerprint,),"promote","v1")
    return k,review,ledger,decision,hr,dispatch


def test_exact_approved_survivor_promotes():
    k,_,_,decision,hr,d=setup()
    out=execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
      surviving_knowledge_ids=(k.knowledge_id,),authorized=True)
    assert out.receipt.passed and out.promoted[0].human_review_id==decision.review_id


def test_changed_survivor_set_invalidates_approval():
    k,_,_,decision,hr,d=setup()
    with pytest.raises(PermissionError,match="survivor set changed"):
        execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(),authorized=True)


def test_failed_adversarial_review_cannot_be_approved():
    _,review,ledger,_,_,_=setup()
    failed=replace(review,receipt=replace(review.receipt,passed=False))
    with pytest.raises(PermissionError,match="cannot be approved"):
        ledger.review("u",failed,reviewer_id="human-1",approved=True,
          reviewed_at=11,rationale="no",authorized=True)


def test_rejected_human_review_cannot_promote():
    k,review,ledger,_,_,_=setup()
    decision,hr=ledger.review("u",review,reviewer_id="human-2",approved=False,
      reviewed_at=12,rationale="reject",authorized=True)
    d=LayerDispatch(AnalysisLayer.MEMORY_PROMOTION,(hr.output_fingerprint,),"promote","v1")
    with pytest.raises(PermissionError,match="human approval"):
        execute_memory_promotion(d,(k,),human_receipt=hr,human_decision=decision,
          surviving_knowledge_ids=(k.knowledge_id,),authorized=True)


def test_probability_threshold_still_applies_after_approval():
    k,_,_,decision,hr,d=setup()
    low=replace(k,probability=.7)
    out=execute_memory_promotion(d,(low,),human_receipt=hr,human_decision=decision,
      surviving_knowledge_ids=(k.knowledge_id,),authorized=True)
    assert not out.promoted and not out.receipt.passed
