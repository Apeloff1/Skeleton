import pytest
from skeleton.frontier.gameforge_rate import RateWindow

def test_rate_window_bounds_requests():
 r=RateWindow(2,10); assert r.allow(0); assert r.allow(1); assert not r.allow(2); assert r.allow(10)

def test_rate_window_exposes_retry_delay():
 r=RateWindow(1,10); assert r.allow(5); assert r.retry_after(7)==8; assert r.remaining(7)==0

def test_rate_window_validates():
 with pytest.raises(ValueError): RateWindow(0)
 with pytest.raises(ValueError): RateWindow(1,0)
