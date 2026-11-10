"""
Phase I.1 — Model Router & Ensemble tests.

Covers the deterministic, no-network surface: the normalised-semantic cache
key (the SOTA enhancement), the TTL/LRU cache mechanics, cost estimation, the
routing policy shape, and the live /policy + /stats HTTP endpoints. The actual
provider completion is exercised separately (needs the LLM key) — here we prove
the routing/caching logic that wraps it.
"""
import os
import time

import pytest
import requests

from routes.llm_router import (
    _canonical, _cache_key, _LRUCache, _estimate_cost,
    ROUTING_POLICY, MODEL_CATALOG,
)


class TestSemanticCacheKey:
    def test_canonical_folds_case_punct_whitespace(self):
        a = _canonical("Reply with exactly one word: PONG")
        b = _canonical("reply   with exactly one word:  pong!!!")
        assert a == b, f"canonical mismatch: {a!r} != {b!r}"

    def test_cache_key_preserves_exact_executable_prompt(self):
        k1 = _cache_key("fast", "", "Reply with exactly one word: PONG")
        k2 = _cache_key("fast", "", "reply with exactly one word: pong!!!")
        assert k1 != k2

    def test_cache_key_differs_by_task(self):
        assert _cache_key("fast", "", "hello") != _cache_key("code", "", "hello")

    def test_cache_key_differs_by_system(self):
        assert _cache_key("fast", "sysA", "hello") != _cache_key("fast", "sysB", "hello")


class TestLRUCache:
    def test_set_get(self):
        c = _LRUCache(maxsize=3, ttl=100)
        c.set("a", {"v": 1})
        assert c.get("a") == {"v": 1}

    def test_ttl_expiry(self):
        c = _LRUCache(maxsize=3, ttl=1)
        c.set("a", 1)
        assert c.get("a") == 1
        time.sleep(1.1)
        assert c.get("a") is None

    def test_lru_eviction(self):
        c = _LRUCache(maxsize=2, ttl=100)
        c.set("a", 1); c.set("b", 2)
        c.get("a")              # touch a → b is now LRU
        c.set("c", 3)           # evicts b
        assert c.get("b") is None
        assert c.get("a") == 1 and c.get("c") == 3

    def test_clear_returns_count(self):
        c = _LRUCache(maxsize=5, ttl=100)
        c.set("a", 1); c.set("b", 2)
        assert c.clear() == 2


class TestPolicyAndCost:
    def test_every_task_targets_known_models(self):
        for task, ensemble in ROUTING_POLICY.items():
            assert ensemble, f"{task} has empty ensemble"
            for m in ensemble:
                assert m in MODEL_CATALOG, f"{task} routes to unknown model {m}"

    def test_default_policy_present(self):
        assert "default" in ROUTING_POLICY

    def test_cost_monotonic_with_size(self):
        small = _estimate_cost("gpt-4o", 100, 100)
        big = _estimate_cost("gpt-4o", 10000, 10000)
        assert big > small >= 0


def _base_url() -> str:
    """Never require a developer's /app/frontend/.env at test collection."""
    base = (
        os.environ.get("EXPO_BACKEND_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or ""
    ).strip().rstrip("/")
    if not base or not base.startswith(("http://", "https://")):
        pytest.skip("Live LLM router test requires an explicit HTTP(S) backend URL")
    return base


@pytest.fixture(scope="module")
def live_backend_url():
    return _base_url()


@pytest.fixture(scope="module")
def live_authenticated_headers():
    token = (os.environ.get("LLM_ROUTER_TEST_BEARER_TOKEN") or "").strip()
    if not token:
        pytest.skip("Private LLM router test requires a credentialed test account")
    return {"Authorization": "Bearer " + token}


@pytest.mark.live_service
class TestLiveEndpoints:
    def test_policy_endpoint(self, live_backend_url, live_authenticated_headers):
        r = requests.get(f"{live_backend_url}/api/llm-router/policy",
                         headers=live_authenticated_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "policy" in d and "models" in d and "key_configured" in d

    def test_stats_endpoint_shape(self, live_backend_url, live_authenticated_headers):
        r = requests.get(f"{live_backend_url}/api/llm-router/stats",
                         headers=live_authenticated_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_calls", "cache_hits", "cache_hit_rate", "by_model", "by_task"):
            assert k in d



def test_zero_cache_budget_disables_reuse_without_eviction_loop():
    cache = _LRUCache(maxsize=0, ttl=120)
    cache.set("a", {"text": "private"})
    assert cache.get("a") is None
    assert cache.clear() == 0


def test_zero_cache_ttl_never_publishes_reusable_results():
    cache = _LRUCache(maxsize=12, ttl=0)
    cache.set("a", {"text": "private"})
    assert cache.get("a") is None
    assert cache.clear() == 0
