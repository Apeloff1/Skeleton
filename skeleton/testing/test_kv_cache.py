"""Focused regressions for the paged KV-cache control plane."""

from __future__ import annotations

import pytest

from skeleton.kv_cache import PagedKVCache


def test_exact_lookup_is_scope_isolated() -> None:
    cache = PagedKVCache(page_size_tokens=2)
    cache.put("model-a", [1, 2], "tenant-a", namespace="tenant-a", adapter_id="lora-1")

    hit = cache.get_exact("model-a", [1, 2], namespace="tenant-a", adapter_id="lora-1")
    assert hit is not None
    assert hit.value == "tenant-a"
    assert cache.get_exact("model-b", [1, 2], namespace="tenant-a", adapter_id="lora-1") is None
    assert cache.get_exact("model-a", [1, 2], namespace="tenant-b", adapter_id="lora-1") is None
    assert cache.get_exact("model-a", [1, 2], namespace="tenant-a", adapter_id="lora-2") is None


def test_longest_prefix_uses_page_boundaries() -> None:
    cache = PagedKVCache(page_size_tokens=2)
    cache.put("model", [10, 11], "page-1")
    cache.put("model", [10, 11, 12, 13], "page-2")

    hit = cache.get_longest_prefix("model", [10, 11, 12, 13, 14])
    assert hit is not None
    assert hit.value == "page-2"
    assert hit.matched_tokens == 4
    assert hit.exact is False


def test_exact_final_partial_page_is_reusable() -> None:
    cache = PagedKVCache(page_size_tokens=4)
    cache.put("model", [1, 2, 3], "partial")

    hit = cache.get_longest_prefix("model", [1, 2, 3])
    assert hit is not None
    assert hit.exact is True
    assert hit.matched_tokens == 3


def test_lru_eviction_respects_recent_hits() -> None:
    cache = PagedKVCache(max_entries=2, ttl_seconds=None)
    cache.put("model", [1], "one")
    cache.put("model", [2], "two")
    assert cache.get_exact("model", [1]) is not None

    cache.put("model", [3], "three")

    assert cache.get_exact("model", [1]) is not None
    assert cache.get_exact("model", [2]) is None
    assert cache.get_exact("model", [3]) is not None
    assert cache.stats()["evictions"] == 1


def test_byte_budget_evicts_oldest_entry() -> None:
    cache = PagedKVCache(max_entries=10, max_bytes=5, ttl_seconds=None)
    cache.put("model", [1], "one", size_bytes=3)
    cache.put("model", [2], "two", size_bytes=3)

    assert cache.get_exact("model", [1]) is None
    assert cache.get_exact("model", [2]) is not None
    assert cache.stats()["bytes"] == 3


def test_ttl_expiry_uses_creation_age() -> None:
    now = [100.0]
    cache = PagedKVCache(ttl_seconds=5.0, clock=lambda: now[0])
    cache.put("model", [1, 2], "value")

    now[0] = 104.9
    assert cache.get_exact("model", [1, 2]) is not None
    now[0] = 105.0
    assert cache.get_exact("model", [1, 2]) is None
    assert cache.stats()["expired"] == 1


def test_targeted_invalidation_does_not_cross_models() -> None:
    cache = PagedKVCache(ttl_seconds=None)
    cache.put("model-a", [1], "a", namespace="tenant")
    cache.put("model-b", [1], "b", namespace="tenant")

    assert cache.invalidate(namespace="tenant", model_id="model-a") == 1
    assert cache.get_exact("model-a", [1], namespace="tenant") is None
    assert cache.get_exact("model-b", [1], namespace="tenant") is not None


def test_invalid_inputs_fail_closed() -> None:
    cache = PagedKVCache()
    with pytest.raises(ValueError):
        cache.put("model", [], "empty")
    with pytest.raises(TypeError):
        cache.put("model", [1, "2"], "bad")  # type: ignore[list-item]
    with pytest.raises(ValueError):
        cache.put("", [1], "bad")
    with pytest.raises(ValueError):
        PagedKVCache(max_bytes=4).put("model", [1], "too-large", size_bytes=5)
