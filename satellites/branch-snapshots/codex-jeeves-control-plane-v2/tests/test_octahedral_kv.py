"""Tests for octahedral KV cache.

Covers entry creation, get/put, eviction, hit rate tracking, and stats.
"""
from __future__ import annotations

import pytest

from skeleton.intelligence.octahedral_kv_cache import CacheEntry, OctahedralKVCache


class TestCacheEntry:
    def test_entry_creation(self):
        entry = CacheEntry(
            key=[0.1] * 64,
            value=[0.2] * 64,
            token_id=1,
            layer=0,
            head=0,
        )
        assert entry.token_id == 1
        assert entry.layer == 0
        assert entry.access_count == 1

    def test_entry_to_dict(self):
        entry = CacheEntry(
            key=[0.1] * 64,
            value=[0.2] * 64,
            token_id=1,
            layer=0,
            head=0,
            attention_score=0.8,
        )
        d = entry.to_dict()
        assert d["token_id"] == 1
        assert d["attention_score"] == 0.8


class TestOctahedralKVCache:
    def test_creation(self):
        cache = OctahedralKVCache(max_entries=1024, layers=6, heads=4)
        assert cache.max_entries == 1024
        assert cache.layers == 6

    def test_put_and_get(self):
        cache = OctahedralKVCache()
        cache.put(1, 0, 0, [0.1] * 64, [0.2] * 64, attention_score=0.9)
        entry = cache.get(1, 0, 0)
        assert entry is not None
        assert entry.token_id == 1
        assert entry.access_count == 2  # 1 initial + 1 from get

    def test_get_miss(self):
        cache = OctahedralKVCache()
        entry = cache.get(999, 0, 0)
        assert entry is None
        assert cache._miss_count == 1

    def test_eviction(self):
        cache = OctahedralKVCache(max_entries=10)
        for i in range(20):
            cache.put(i, 0, 0, [0.1] * 64, [0.2] * 64)
        assert len(cache._entries) <= 10

    def test_hit_rate(self):
        cache = OctahedralKVCache()
        cache.put(1, 0, 0, [0.1] * 64, [0.2] * 64)
        cache.get(1, 0, 0)  # hit
        cache.get(2, 0, 0)  # miss
        stats = cache.stats()
        assert stats["hit_rate"] == 0.5
        assert stats["miss_rate"] == 0.5

    def test_attention_priority(self):
        cache = OctahedralKVCache(max_entries=4)
        # Put low-attention entries first
        for i in range(4):
            cache.put(i, 0, 0, [0.1] * 64, [0.2] * 64, attention_score=0.1)
        # Put high-attention entry
        cache.put(100, 0, 0, [0.1] * 64, [0.2] * 64, attention_score=0.99)
        # High attention should be kept
        assert cache.get(100, 0, 0) is not None

    def test_stats(self):
        cache = OctahedralKVCache()
        stats = cache.stats()
        assert stats["entries"] == 0
        assert stats["max_entries"] == 4096

    def test_card(self):
        cache = OctahedralKVCache()
        card = cache.card()
        assert card["kind"] == "octahedral-kv-cache-card"
        assert card["entries"] == 0
