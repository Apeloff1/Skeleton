import pytest
from skeleton.frontier.gameforge_rate import RateWindow

def test_rate_window_bounds_requests():
 r=RateWindow(2,10); assert r.allow(0); assert r.allow(1); assert not r.allow(2); assert r.allow(10)

def test_rate_window_validates():
 with pytest.raises(ValueError): RateWindow(0)
 with pytest.raises(ValueError): RateWindow(1,0)
