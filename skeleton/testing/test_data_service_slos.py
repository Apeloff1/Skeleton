from skeleton.observability.data_slos import *
def test_stale_but_available_is_not_healthy_data():
 h=health(available=True,freshness=FreshnessSLI(120,60),correct=True);assert h.available and not h.fresh
def test_correctness_failure_remains_visible():
 assert not health(available=True,freshness=FreshnessSLI(1,60),correct=False).correct

def test_invalid_slo_probability_and_negative_age_rejected():
 import pytest
 with pytest.raises(ValueError):DataSLO(1.1,1,1)
 with pytest.raises(ValueError):FreshnessSLI(-1,10)
