import pytest
from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.quotas import QuotaPolicy, TenantQuotas


def test_bucket_refill_and_isolation():
    now = [0.0]
    q = TenantQuotas({"default": QuotaPolicy(1, 2)}, clock=lambda: now[0])
    q.check("a", "default")
    q.check("a", "default")
    with pytest.raises(EdgeError) as e:
        q.check("a", "default")
    assert e.value.status == 429 and e.value.headers["retry-after"] == "1"
    q.check("b", "default")  # other tenant unaffected
    now[0] = 1.0
    q.check("a", "default")


def test_window_quota_and_override():
    now = [0.0]
    q = TenantQuotas({"default": QuotaPolicy(100, 100, window_s=60, window_limit=2)},
                     overrides={("vip", "default"): QuotaPolicy(100, 100)}, clock=lambda: now[0])
    assert q.check("a", "default")["x-quota-remaining"] == "1"
    q.check("a", "default")
    with pytest.raises(EdgeError) as e:
        q.check("a", "default")
    assert e.value.code == "EDGE.QUOTA.EXHAUSTED"
    for _ in range(5):
        q.check("vip", "default")
    now[0] = 61
    q.check("a", "default")
    assert q.usage("a") == {"default": 1}


def test_policy_validation_and_eviction():
    with pytest.raises(ValueError):
        QuotaPolicy(0, 1)
    with pytest.raises(ValueError):
        QuotaPolicy(1, 0)
    with pytest.raises(ValueError):
        QuotaPolicy(1, 1, window_s=0)
    with pytest.raises(ValueError):
        QuotaPolicy(1, 1, window_s=float("nan"))
    with pytest.raises(ValueError):
        TenantQuotas({})
    with pytest.raises(ValueError):
        TenantQuotas({"default": QuotaPolicy(1, 1)}, max_buckets=0)
    now = [0.0]
    q = TenantQuotas({"default": QuotaPolicy(1, 1)}, max_buckets=10, clock=lambda: now[0])
    for i in range(10):
        q.check(f"t{i}", "default")
    with pytest.raises(EdgeError) as capacity:
        q.check("extra", "default")
    assert capacity.value.code == "EDGE.QUOTA.CAPACITY" and capacity.value.status == 503
    with pytest.raises(EdgeError) as retained:
        q.check("t0", "default")
    assert retained.value.status == 429  # tenant allowance not reset on capacity
    now[0] = 2.0
    q.check("extra", "default")
    assert len(q._buckets) <= 10


def test_legacy_window_history_not_evicted_until_expiry():
    now = [0.0]
    q = TenantQuotas(
        {"default": QuotaPolicy(100, 1, window_s=30, window_limit=1)},
        max_buckets=1, clock=lambda: now[0]
    )
    q.check("a", "default")
    now[0] = 2.0  # burst refilled, but window custody still active
    with pytest.raises(EdgeError) as capacity:
        q.check("b", "default")
    assert capacity.value.code == "EDGE.QUOTA.CAPACITY"
    now[0] = 31.0
    q.check("b", "default")


def test_legacy_quota_concurrent_requests_have_single_budget():
    from concurrent.futures import ThreadPoolExecutor
    q = TenantQuotas({"default": QuotaPolicy(0.001, 5)}, clock=lambda: 0.0)
    def take(_):
        try:
            q.check("same", "default")
            return 1
        except EdgeError as err:
            assert err.status == 429
            return 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        result = list(pool.map(take, range(200)))
    assert sum(result) == 5


def test_legacy_quota_clock_rollback_does_not_mint_tokens():
    now = [1000.0]
    q = TenantQuotas({"default": QuotaPolicy(1.0, 2)}, clock=lambda: now[0])
    q.check("a", "default")
    q.check("a", "default")
    now[0] = 0.0
    with pytest.raises(EdgeError):
        q.check("a", "default")
    now[0] = 1000.0
    with pytest.raises(EdgeError):
        q.check("a", "default")
    now[0] = 1001.0
    assert q.check("a", "default")["ratelimit-remaining"] == "0"
