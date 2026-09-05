"""Tests for octahedral KV cache."""
from __future__ import annotations

import pytest

from skeleton.intelligence.octahedral_kv_cache import CacheEntry, OctahedralKVCache


class TestCacheEntry:
    def test_to_dict(self):
        e = CacheEntry(key=[1.0], value=[2.0], token_id=5, layer=1, head=2, attention_score=0.8)
        d = e.to_dict()
        assert d["token_id"] == 5
        assert d["layer"] == 1
        assert d["head"] == 2
        assert d["attention_score"] == 0.8


class TestOctahedralKVCache:
    def test_put_and_get(self):
        cache = OctahedralKVCache(max_entries=100)
        cache.put(1, 0, 0, [1.0, 2.0], [3.0, 4.0], attention_score=0.9)
        entry = cache.get(1, 0, 0)
        assert entry is not None
        assert entry.token_id == 1
        assert entry.access_count == 1

    def test_get_miss(self):
        cache = OctahedralKVCache(max_entries=100)
        assert cache.get(1, 0, 0) is None

    def test_get_updates_access(self):
        cache = OctahedralKVCache(max_entries=100)
        cache.put(1, 0, 0, [1.0], [2.0])
        cache.get(1, 0, 0)
        entry = cache.get(1, 0, 0)
        assert entry.access_count == 3  # initial + 2 gets

    def test_eviction(self):
        cache = OctahedralKVCache(max_entries=10)
        for i in range(15):
            cache.put(i, 0, 0, [1.0], [2.0], attention_score=0.1)
        assert len(cache._entries) <= 10

    def test_stats(self):
        cache = OctahedralKVCache(max_entries=100)
        cache.put(1, 0, 0, [1.0], [2.0])
        cache.get(1, 0, 0)
        stats = cache.stats()
        assert stats["entries"] == 1
        assert stats["hit_rate"] == 0.5  # 1 hit, 1 miss (initial put doesn't count)

    def test_card(self):
        cache = OctahedralKVCache(max_entries=100)
        card = cache.card()
        assert card["kind"] == "octahedral-kv-cache-card"
        assert card["max_entries"] == 100

    def test_eviction_respects_attention(self):
        cache = OctahedralKVCache(max_entries=5)
        # High attention entry
        cache.put(100, 0, 0, [1.0], [2.0], attention_score=0.99)
        # Fill cache with low attention entries
        for i in range(10):
            cache.put(i, 0, 0, [1.0], [2.0], attention_score=0.01)
        # High attention entry should survive
        assert cache.get(100, 0, 0) is not None
