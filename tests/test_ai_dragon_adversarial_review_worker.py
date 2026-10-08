"""Adversarial-review regressions."""
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import NormalizedKnowledge
from skeleton.ai.webcrawler.dragon_adversarial_review_worker import execute_adversarial_review
from skeleton.ai.webcrawler.dragon_knowledge_manifest import canonical_knowledge_id


def base():
    receipt=LayerReceipt(AnalysisLayer.KNOWLEDGE_NORMALIZATION,("a"*64,),"b"*64,2,True,False)
    dispatch=LayerDispatch(AnalysisLayer.ADVERSARIAL_REVIEW,("b"*64,),"redteam","v1")
    record=NormalizedKnowledge("","h","v1","supported",.8,
        "empirically_calibrated_probability","d"*64,"e"*64,"resolved_support")
    record=replace(record,knowledge_id=canonical_knowledge_id(record))
    return receipt,dispatch,record


def test_clean_record_survives_all_attacks():
    r,d,k=base(); out=execute_adversarial_review(d,(k,),
        normalization_receipt=r,authorized=True)
    assert out.surviving_knowledge_ids==(k.knowledge_id,)
    assert out.receipt.passed
    assert all(x.passed for x in out.findings)


def test_unresolved_contradiction_is_rejected():
    r,d,k=base(); out=execute_adversarial_review(d,(replace(k,
        contradiction_state="unresolved"),),normalization_receipt=r,authorized=True)
    assert not out.receipt.passed
    assert any(x.attack=="contradiction_suppression" and not x.passed for x in out.findings)


def test_calibration_semantics_attack_detects_relabelling():
    r,d,k=base(); out=execute_adversarial_review(d,(replace(k,
        probability_semantics="heuristic_logistic_score"),),
        normalization_receipt=r,authorized=True)
    assert any(x.attack=="probability_semantics" and not x.passed for x in out.findings)


def test_duplicate_hypothesis_cannot_masquerade_as_two_records():
    r,d,k=base(); other=replace(k,knowledge_id="f"*64)
    out=execute_adversarial_review(d,(k,other),normalization_receipt=r,authorized=True)
    assert not out.receipt.passed
    assert any(x.attack=="hypothesis_duplication" and not x.passed for x in out.findings)


def test_same_id_changed_content_is_rejected_at_adversarial_boundary():
    r,d,k=base()
    forged=replace(k,probability=.7)
    out=execute_adversarial_review(d,(forged,),normalization_receipt=r,authorized=True)
    assert not out.receipt.passed
    assert any(x.attack=="identity_integrity" and not x.passed for x in out.findings)


def test_recomputed_identity_for_changed_content_is_canonical():
    r,d,k=base()
    changed=replace(k,knowledge_id="",probability=.7)
    changed=replace(changed,knowledge_id=canonical_knowledge_id(changed))
    out=execute_adversarial_review(d,(changed,),normalization_receipt=r,authorized=True)
    assert all(x.passed for x in out.findings)
    assert out.surviving_knowledge_ids==(changed.knowledge_id,)
