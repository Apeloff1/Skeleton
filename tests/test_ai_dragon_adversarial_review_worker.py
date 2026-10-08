"""Adversarial-review regressions."""
from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import (
    NormalizedKnowledge,normalization_records_fingerprint)
from skeleton.ai.webcrawler.dragon_adversarial_review_worker import execute_adversarial_review
from skeleton.ai.webcrawler.dragon_knowledge_manifest import canonical_knowledge_id


INPUT=("a"*64,)

def record(**changes):
    item=NormalizedKnowledge("","h","v1","supported",.8,
        "empirically_calibrated_probability","d"*64,"e"*64,"resolved_support")
    item=replace(item,knowledge_id=canonical_knowledge_id(item))
    if changes:
        item=replace(item,**changes)
    return item

def bound(records):
    fp=normalization_records_fingerprint(INPUT,records)
    receipt=LayerReceipt(AnalysisLayer.KNOWLEDGE_NORMALIZATION,INPUT,fp,2,True,False)
    dispatch=LayerDispatch(AnalysisLayer.ADVERSARIAL_REVIEW,(fp,),"redteam","v1")
    return receipt,dispatch


def test_clean_record_survives_all_attacks():
    k=record();r,d=bound((k,))
    out=execute_adversarial_review(d,(k,),normalization_receipt=r,authorized=True)
    assert out.surviving_knowledge_ids==(k.knowledge_id,)
    assert out.receipt.passed
    assert all(x.passed for x in out.findings)


def test_unresolved_contradiction_is_rejected():
    k=record(contradiction_state="unresolved");r,d=bound((k,))
    out=execute_adversarial_review(d,(k,),normalization_receipt=r,authorized=True)
    assert not out.receipt.passed
    assert any(x.attack=="contradiction_suppression" and not x.passed for x in out.findings)


def test_calibration_semantics_attack_detects_relabelling():
    k=record(probability_semantics="heuristic_logistic_score");r,d=bound((k,))
    out=execute_adversarial_review(d,(k,),normalization_receipt=r,authorized=True)
    assert any(x.attack=="probability_semantics" and not x.passed for x in out.findings)


def test_duplicate_hypothesis_cannot_masquerade_as_two_records():
    k=record()
    other=replace(k,knowledge_id="f"*64)
    r,d=bound((k,other))
    out=execute_adversarial_review(d,(k,other),normalization_receipt=r,authorized=True)
    assert not out.receipt.passed
    assert any(x.attack=="hypothesis_duplication" and not x.passed for x in out.findings)


def test_same_id_changed_content_is_rejected_before_adversarial_scoring():
    original=record();r,d=bound((original,))
    forged=replace(original,probability=.7)
    with pytest.raises(ValueError,match="record set does not match"):
        execute_adversarial_review(d,(forged,),normalization_receipt=r,authorized=True)


def test_recomputed_identity_for_changed_content_still_cannot_substitute_receipt():
    original=record();r,d=bound((original,))
    changed=replace(original,knowledge_id="",probability=.7)
    changed=replace(changed,knowledge_id=canonical_knowledge_id(changed))
    assert changed.knowledge_id!=original.knowledge_id
    with pytest.raises(ValueError,match="record set does not match"):
        execute_adversarial_review(d,(changed,),normalization_receipt=r,authorized=True)


def test_genuinely_normalized_changed_record_can_be_reviewed():
    changed=record()
    changed=replace(changed,knowledge_id="",probability=.7)
    changed=replace(changed,knowledge_id=canonical_knowledge_id(changed))
    r,d=bound((changed,))
    out=execute_adversarial_review(d,(changed,),normalization_receipt=r,authorized=True)
    assert out.surviving_knowledge_ids==(changed.knowledge_id,)
