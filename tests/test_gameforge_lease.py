import pytest
from skeleton.frontier.gameforge_lease import LeaseSet

def test_lease_set_is_bounded_and_releases():
    s=LeaseSet(1); a=s.acquire("a"); assert a; assert s.acquire("b") is None; a.release(); assert s.active==0; b=s.acquire("b"); assert b

def test_lease_cannot_release_twice():
    a=LeaseSet().acquire("a"); a.release()
    with pytest.raises(RuntimeError): a.release()
