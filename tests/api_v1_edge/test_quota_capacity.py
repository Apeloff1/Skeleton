"""Fail-closed quota admission under tenant churn and concurrent calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.quotas import QuotaPolicy, TenantQuotas


def test_live_tenant_cannot_be_evicted_to_reset_quota():
    now = [100.0]
    quotas = TenantQuotas(
        {"default": QuotaPolicy(1.0, 1, window_s=10.0, window_limit=1)},
        max_buckets=1, clock=lambda: now[0],
    )
    quotas.check("tenant-a", "default")
    with pytest.raises(EdgeError) as full:
        quotas.check("tenant-b", "default")
    assert full.value.status == 503 and full.value.code == "EDGE.QUOTA.CAPACITY"
    with pytest.raises(EdgeError) as exhausted:
        quotas.check("tenant-a", "default")
    assert exhausted.value.status == 429 and exhausted.value.code == "EDGE.QUOTA.EXHAUSTED"
    assert quotas.usage("tenant-a") == {"default": 1}
    now[0] = 111.0
    assert quotas.check("tenant-b", "default")["x-quota-remaining"] == "0"
    assert quotas.usage("tenant-a") == {}


def test_rollback_clock_does_not_free_live_quota():
    now = [100.0]
    quotas = TenantQuotas({"default": QuotaPolicy(1.0, 1, window_s=10.0)}, max_buckets=1,
                          clock=lambda: now[0])
    quotas.check("a", "default")
    now[0] = 50.0
    with pytest.raises(EdgeError) as exc:
        quotas.check("b", "default")
    assert exc.value.code == "EDGE.QUOTA.CAPACITY"


def test_parallel_quota_consumption_is_atomic():
    quotas = TenantQuotas({"default": QuotaPolicy(1.0, 1, window_s=60.0, window_limit=1)})
    barrier = Barrier(2)

    def attempt():
        barrier.wait()
        try:
            quotas.check("same", "default")
            return "accepted"
        except EdgeError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["EDGE.QUOTA.EXHAUSTED", "accepted"]


def test_invalid_bucket_capacity_fails_fast():
    for value in (0, -1, True):
        with pytest.raises(ValueError):
            TenantQuotas({"default": QuotaPolicy(1.0, 1)}, max_buckets=value)


@pytest.mark.parametrize("kwargs", [
    {"rate_per_s": True}, {"rate_per_s": float("nan")},
    {"rate_per_s": float("inf")}, {"rate_per_s": 0},
    {"burst": True}, {"burst": 0}, {"window_s": 0},
    {"window_s": float("nan")}, {"window_s": float("inf")},
    {"window_limit": True}, {"window_limit": 0},
])
def test_invalid_quota_policy_fails_closed(kwargs):
    with pytest.raises(ValueError):
        QuotaPolicy(**{"rate_per_s": 1.0, "burst": 1, **kwargs})
