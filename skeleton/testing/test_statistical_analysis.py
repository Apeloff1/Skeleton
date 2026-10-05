from __future__ import annotations
import pytest
from skeleton.ai.evaluation.statistical_analysis import SampleSeries,StatisticalAnalysis,StatisticalAnalysisError,paired_difference,summarize

def test_descriptive_analysis_is_deterministic():
    report=summarize(SampleSeries("s","bench","score",(1.0,2.0,3.0)))
    assert report.method=="descriptive"
    assert report.mean==pytest.approx(2.0)
    assert report.median==pytest.approx(2.0)
    assert len(report.digest)==64

def test_paired_difference_requires_identity_and_equal_counts():
    baseline=SampleSeries("a","bench","score",(1.0,2.0))
    candidate=SampleSeries("b","bench","score",(2.0,4.0))
    result=paired_difference(baseline,candidate)
    assert result.effect==pytest.approx(1.5)
    with pytest.raises(StatisticalAnalysisError,match="equal sample counts"):
        paired_difference(baseline,SampleSeries("c","bench","score",(2.0,)))
    with pytest.raises(StatisticalAnalysisError,match="identical benchmark"):
        paired_difference(baseline,SampleSeries("d","other","score",(2.0,4.0)))

def test_unapproved_statistical_method_is_rejected():
    with pytest.raises(StatisticalAnalysisError,match="unapproved"):
        StatisticalAnalysis("p-hack","a"*64,None,1,1.0,1.0,0.0,None)

def test_nonfinite_samples_are_rejected():
    with pytest.raises(StatisticalAnalysisError,match="finite"):
        SampleSeries("s","b","m",(float("nan"),))
