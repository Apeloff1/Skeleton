import pytest

from skeleton.api.v1_edge.quota_store import Limit, QuotaPlan, TakeResult, route_key, tenant_digest
from skeleton.api.v1_edge.quota_store.headers import (denial_headers, merge_legacy,
                                                      most_restrictive, quota_headers,
                                                      retry_after_value)
from skeleton.api.v1_edge.quota_store.policy import Bucket


def test_limit_helpers_and_validation():
    assert Limit.per_minute(60).rate_per_s == 1 and Limit.per_minute(60).burst == 60
    assert Limit.per_hour(3600, burst=10).burst == 10
    assert Limit(1, 30).window_s == 30
    with pytest.raises(ValueError):
        Limit(0, 1)
    with pytest.raises(ValueError):
        Limit(1, 0)


def test_plan_validation():
    with pytest.raises(ValueError):
        QuotaPlan({})
    with pytest.raises(ValueError):
        QuotaPlan({"default": Limit(1, 1)}, route_limits={"/no-method": Limit(1, 1)})
    with pytest.raises(ValueError):
        QuotaPlan({"default": Limit(1, 1)}, method_cost={"POST": 0})


def test_buckets_narrowest_first_and_overrides():
    plan = QuotaPlan({"default": Limit(10, 10), "writes": Limit(1, 5)},
                     tenant_overrides={("vip", "writes"): Limit(5, 50)},
                     route_limits={"POST /projects": Limit(100, 100)},
                     tenant_route_limits={"POST /projects": Limit(2, 3)},
                     tenant_route_overrides={("vip", "POST /projects"): Limit(5, 9)})
    bs = plan.buckets("t1", "writes", "post", "/projects")
    assert [b.scope for b in bs] == ["route", "tenant_route", "tenant"]
    assert bs[2].limit.burst == 5 and bs[1].limit.burst == 3
    vip = plan.buckets("vip", "writes", "POST", "/projects")
    assert vip[1].limit.burst == 9 and vip[2].limit.burst == 50
    assert [b.scope for b in plan.buckets("t1", "other", "GET", "/x")] == ["tenant"]
    assert plan.buckets("t1", "other", "GET", "/x")[0].limit.burst == 10


def test_keys_hash_tenants_and_use_templates():
    plan = QuotaPlan({"default": Limit(1, 1)}, tenant_route_limits={"GET /p/{id}": Limit(1, 1)})
    raw = "evil:tenant\nx"
    keys = [b.key for b in plan.buckets(raw, "default", "GET", "/p/{id}")]
    assert all(raw not in k for k in keys)
    assert tenant_digest(raw) in keys[0] and "GET /p/{id}" in keys[0]
    assert tenant_digest(None) == tenant_digest("anonymous")
    assert route_key("get", "/a") == "GET /a"
    assert plan.cost_for("GET") == 1.0


def _pair(scope, burst, remaining, reset, retry=0.0, allowed=True):
    b = Bucket(scope, scope, Limit(1, burst), scope)
    return b, TakeResult(allowed, remaining, burst, retry, reset)


def test_quota_headers_pick_most_restrictive():
    pairs = [_pair("route", 100, 90, 10), _pair("tenant", 5, 2, 3)]
    h = quota_headers(pairs)
    assert h["ratelimit-limit"] == "5" and h["ratelimit-remaining"] == "2"
    assert h["ratelimit-reset"] == "3"
    assert h["ratelimit-policy"] == '"route";q=100;w=100, "tenant";q=5;w=5'
    assert quota_headers([]) == {}
    assert most_restrictive([]) is None


def test_denial_headers_and_retry_after():
    ok = _pair("tenant_route", 3, 1, 2)
    denied = _pair("tenant", 5, 0.4, 4.6, retry=0.6, allowed=False)
    h = denial_headers([ok, denied], denied)
    assert h["ratelimit-remaining"] == "0" and h["retry-after"] == "1"
    assert h["x-ratelimit-scope"] == "tenant" and h["ratelimit-limit"] == "5"
    assert retry_after_value(float("inf")) == "86400"
    assert retry_after_value(0) == "1"


def test_merge_legacy_keeps_window_header_and_lowest_remaining():
    legacy = {"ratelimit-limit": "10", "ratelimit-remaining": "1", "x-quota-remaining": "7"}
    new = {"ratelimit-limit": "50", "ratelimit-remaining": "40", "ratelimit-reset": "2",
           "ratelimit-policy": '"tenant";q=50;w=50'}
    m = merge_legacy(legacy, new)
    assert m["ratelimit-remaining"] == "1" and m["x-quota-remaining"] == "7"
    assert m["ratelimit-policy"].startswith('"tenant"') and "ratelimit-reset" not in m
    m2 = merge_legacy({"x-quota-remaining": "3"}, new)
    assert m2["ratelimit-remaining"] == "40"
    assert merge_legacy(legacy, {}) == legacy
