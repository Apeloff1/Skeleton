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
        TenantQuotas({})
    q = TenantQuotas({"default": QuotaPolicy(1, 1)}, max_buckets=10)
    for i in range(30):
        q.check(f"t{i}", "default")
    assert len(q._buckets) <= 10
