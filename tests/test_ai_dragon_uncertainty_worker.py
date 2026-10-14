"""Executable uncertainty-calibration regressions."""
from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_cross_source_worker import CorroboratedClaim
from skeleton.ai.webcrawler.dragon_empirical_calibration import fit_histogram_calibrator
from skeleton.ai.webcrawler.dragon_probability_calibration import CalibrationExample
from skeleton.ai.webcrawler.dragon_uncertainty_worker import execute_uncertainty_calibration


def artifact():
    rows=[]
    # Dense two-bin calibration with disjoint train/eval periods.
    for period in ("train","eval"):
        for i in range(20):
            p=.25 if i<10 else .75
            truth=i>=10
            rows.append(CalibrationExample(f"{period}-{i}",p,truth,"g",period))
    return fit_histogram_calibrator(tuple(rows),training_periods=("train",),
        evaluation_periods=("eval",),authorized=True,bins=2,
        minimum_bin_samples=10,minimum_evaluation_samples=20,maximum_ece=.3)


def inputs():
    r=LayerReceipt(AnalysisLayer.CROSS_SOURCE_CORROBORATION,("a"*64,),"b"*64,2,True,False)
    d=LayerDispatch(AnalysisLayer.UNCERTAINTY_CALIBRATION,("b"*64,),"cal","v1")
    c=(CorroboratedClaim("h","supported",("x","y"),(),(),True),)
    return r,d,c


def test_emits_empirical_semantics_and_artifact_identity():
    r,d,c=inputs(); a=artifact()
    out=execute_uncertainty_calibration(d,c,corroboration_receipt=r,
        raw_scores={"h":.8},artifact=a,authorized=True)
    assert out.claims[0].probability_semantics=="empirically_calibrated_heldout_probability"
    assert out.claims[0].calibration_artifact_fingerprint==a.artifact_fingerprint


def test_ineligible_artifact_fails_closed():
    r,d,c=inputs(); a=replace(artifact(),eligible=False)
    with pytest.raises(ValueError,match="not eligible"):
        execute_uncertainty_calibration(d,c,corroboration_receipt=r,
            raw_scores={"h":.8},artifact=a,authorized=True)


def test_score_inventory_must_exactly_match_claims():
    r,d,c=inputs()
    with pytest.raises(ValueError,match="exactly match"):
        execute_uncertainty_calibration(d,c,corroboration_receipt=r,
            raw_scores={"other":.8},artifact=artifact(),authorized=True)


def test_dependency_substitution_fails_closed():
    r,d,c=inputs(); bad=LayerDispatch(AnalysisLayer.UNCERTAINTY_CALIBRATION,
        ("c"*64,),"cal","v1")
    with pytest.raises(ValueError,match="mismatch"):
        execute_uncertainty_calibration(bad,c,corroboration_receipt=r,
            raw_scores={"h":.8},artifact=artifact(),authorized=True)
