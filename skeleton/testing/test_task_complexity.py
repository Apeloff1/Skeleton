import pytest
from skeleton.ai.task_complexity import *
def f(v,w=1):return ComplexityFeature("x",v,w)
def test_estimate_exposes_uncertainty_and_calibration():
 e=estimate_complexity((f(3),),calibration_version="cal:v1",hard_limit=5,uncertainty=.2)
 assert e.score==3 and e.uncertainty==.2 and e.calibration_version=="cal:v1"
def test_underestimate_revision_cannot_raise_hard_limit():
 old=estimate_complexity((f(1),),calibration_version="v1",hard_limit=5,uncertainty=.5)
 r=revise_estimate(old,(f(8),),reason="runtime evidence",uncertainty=.1)
 assert old.admitted and not r.revised.admitted and r.revised.hard_limit==5
def test_revision_cannot_forge_limit():
 old=estimate_complexity((f(1),),calibration_version="v1",hard_limit=5,uncertainty=.5)
 forged=ComplexityEstimate(1,.1,"v1",(),9)
 with pytest.raises(ValueError):EstimateRevision(old,forged,"forged")
def test_invalid_uncertainty_and_features_fail_closed():
 with pytest.raises(ValueError):estimate_complexity((f(1),),calibration_version="v1",hard_limit=5,uncertainty=2)
 with pytest.raises(ValueError):ComplexityFeature("x",-1,1)
