import pytest
from skeleton.automation.studio_health import StudioHealth
def test_health():
 assert StudioHealth(1,1,0,0,0,0).healthy
 assert not StudioHealth(1,1,0,0,1,0).healthy
def test_negative_rejected():
 with pytest.raises(ValueError): StudioHealth(-1,0,0,0,0,0)
