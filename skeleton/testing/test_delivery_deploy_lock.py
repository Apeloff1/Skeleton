import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.deploy_lock import DeployLockTable


def test_acquire_conflict_expiry_and_fencing():
    t = DeployLockTable()
    a = t.acquire("prod", "alice", now=0, ttl=10)
    with pytest.raises(DeliveryError, match="locked"):
        t.acquire("prod", "bob", now=5, ttl=10)
    b = t.acquire("prod", "bob", now=11, ttl=10)
    assert b.token == a.token + 1
    with pytest.raises(DeliveryError, match="stale"):
        t.release(a, now=12)
    t.release(b, now=12)
    assert t.holder("prod", now=12) is None


def test_renew_and_ttl_bounds():
    t = DeployLockTable()
    a = t.acquire("dev", "ci", now=0, ttl=10)
    r = t.renew(a, now=9, ttl=10)
    assert r.expires_at == 19 and r.token == a.token
    with pytest.raises(DeliveryError):
        t.acquire("dev2", "ci", now=0, ttl=0)
    with pytest.raises(DeliveryError):
        t.renew(r, now=100, ttl=10)
