from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


def test_deploy_lock_rejects_invalid_clocks_and_boolean_ttls():
    t = DeployLockTable()
    with pytest.raises(DeliveryError, match="clock"):
        t.acquire("dev", "ci", now=True, ttl=10)
    with pytest.raises(DeliveryError, match="clock"):
        t.holder("dev", now=-1)
    with pytest.raises(DeliveryError, match="ttl"):
        t.acquire("dev", "ci", now=0, ttl=True)
    lease = t.acquire("dev", "ci", now=0, ttl=10)
    with pytest.raises(DeliveryError, match="ttl"):
        t.renew(lease, now=1, ttl=True)


def test_renewed_lease_rejects_stale_pre_renewal_release():
    t = DeployLockTable()
    original = t.acquire("prod", "alice", now=0, ttl=10)
    renewed = t.renew(original, now=5, ttl=10)
    assert renewed.token == original.token and renewed.expires_at == 15
    with pytest.raises(DeliveryError, match="stale"):
        t.release(original, now=6)
    with pytest.raises(DeliveryError, match="stale"):
        t.renew(original, now=6, ttl=10)
    t.release(renewed, now=6)
    assert t.holder("prod", now=6) is None


def test_parallel_acquires_have_one_owner_and_one_fencing_token():
    table = DeployLockTable()
    workers = 12
    gate = Barrier(workers)

    def contender(index: int):
        gate.wait(timeout=10)
        try:
            return table.acquire("prod", f"worker-{index}", now=1, ttl=30)
        except DeliveryError:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(contender, range(workers)))
    winners = [lease for lease in results if lease is not None]
    assert len(winners) == 1
    assert winners[0].token == 1
    assert table.holder("prod", now=1) == winners[0]
