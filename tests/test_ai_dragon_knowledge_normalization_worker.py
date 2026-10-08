"""Knowledge-normalization regressions."""
from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_uncertainty_calibration_worker import CalibratedClaim
from skeleton.ai.webcrawler.dragon_knowledge_normalization_worker import execute_knowledge_normalization


def base(verdict="supported"):
    r=LayerReceipt(AnalysisLayer.UNCERTAINTY_CALIBRATION,("a"*64,),"b"*64,2,True,False)
    d=LayerDispatch(AnalysisLayer.KNOWLEDGE_NORMALIZATION,("b"*64,),"normalize","v1")
    c=CalibratedClaim("h",verdict,.8,.73,
        "empirically_calibrated_probability","c"*64)
    return r,d,c


def test_preserves_calibration_and_evidence_identity():
    r,d,c=base(); x=execute_knowledge_normalization(
        d,(c,),calibration_receipt=r,authorized=True).records[0]
    assert x.calibration_artifact_fingerprint=="c"*64
    assert x.evidence_fingerprint==r.output_fingerprint
    assert x.probability_semantics=="empirically_calibrated_probability"


def test_unresolved_contradiction_survives_normalization():
    r,d,c=base("inconclusive"); x=execute_knowledge_normalization(
        d,(c,),calibration_receipt=r,authorized=True).records[0]
    assert x.contradiction_state=="unresolved"


def test_heuristic_probability_cannot_be_relabelled():
    r,d,c=base()
    with pytest.raises(ValueError,match="non-calibrated"):
        execute_knowledge_normalization(d,(replace(c,
            probability_semantics="heuristic_logistic_score"),),
            calibration_receipt=r,authorized=True)


def test_ontology_version_changes_knowledge_identity():
    r,d,c=base()
    a=execute_knowledge_normalization(d,(c,),calibration_receipt=r,
        authorized=True,ontology_version="v1").records[0]
    b=execute_knowledge_normalization(d,(c,),calibration_receipt=r,
        authorized=True,ontology_version="v2").records[0]
    assert a.knowledge_id!=b.knowledge_id
