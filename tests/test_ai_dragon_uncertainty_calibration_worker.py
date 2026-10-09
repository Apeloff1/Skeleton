"""Uncertainty-calibration worker regressions."""
from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_cross_source_worker import CorroboratedClaim
from skeleton.ai.webcrawler.dragon_empirical_calibration import fit_histogram_calibrator
from skeleton.ai.webcrawler.dragon_probability_calibration import CalibrationExample
from skeleton.ai.webcrawler.dragon_uncertainty_calibration_worker import execute_uncertainty_calibration


def setup():
    examples=[]
    # Dense deterministic bins with disjoint train/eval periods.
    for i in range(100):
        score=(i%10+.5)/10
        truth=score>=.5
        examples.append(CalibrationExample(f"tr{i}",score,truth,f"s{i%3}","train"))
    for i in range(50):
        score=(i%10+.5)/10
        truth=score>=.5
        examples.append(CalibrationExample(f"ev{i}",score,truth,f"s{i%3}","eval"))
    artifact=fit_histogram_calibrator(tuple(examples),training_periods=("train",),
        evaluation_periods=("eval",),authorized=True,bins=10,
        minimum_bin_samples=10,minimum_evaluation_samples=30,maximum_ece=.6)
    r=LayerReceipt(AnalysisLayer.CROSS_SOURCE_CORROBORATION,("a"*64,),"b"*64,2,True,False)
    d=LayerDispatch(AnalysisLayer.UNCERTAINTY_CALIBRATION,("b"*64,),"cal","v1")
    c=(CorroboratedClaim("h","supported",("x","y"),(),(),True),)
    return artifact,r,d,c


def test_emits_empirical_semantics_and_artifact_identity():
    a,r,d,c=setup(); out=execute_uncertainty_calibration(
        d,c,{"h":.85},corroboration_receipt=r,artifact=a,authorized=True)
    assert out.claims[0].probability_semantics=="empirically_calibrated_probability"
    assert out.claims[0].calibration_artifact_fingerprint==a.artifact_fingerprint


def test_ineligible_artifact_fails_closed():
    a,r,d,c=setup()
    with pytest.raises(ValueError,match="not eligible"):
        execute_uncertainty_calibration(d,c,{"h":.85},corroboration_receipt=r,
            artifact=replace(a,eligible=False),authorized=True)


def test_score_coverage_must_be_exact():
    a,r,d,c=setup()
    with pytest.raises(ValueError,match="exactly"):
        execute_uncertainty_calibration(d,c,{},corroboration_receipt=r,
            artifact=a,authorized=True)


def test_dependency_substitution_fails():
    a,r,d,c=setup()
    bad=LayerDispatch(AnalysisLayer.UNCERTAINTY_CALIBRATION,("c"*64,),"cal","v1")
    with pytest.raises(ValueError,match="mismatch"):
        execute_uncertainty_calibration(bad,c,{"h":.8},
            corroboration_receipt=r,artifact=a,authorized=True)
