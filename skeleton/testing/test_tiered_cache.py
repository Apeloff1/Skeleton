"""Tests for skeleton.kernel.tiered_cache (gameforge-rs cache::TieredCache port)."""

from __future__ import annotations

import time

from skeleton.kernel.tiered_cache import (
    L1_CAP,
    L1_TTL_S,
    L2_CAP,
    L2_TTL_S,
    TieredCache,
)


def test_caps_and_ttls_match_rs():
    assert L1_CAP == 512
    assert L2_CAP == 4096
    assert L1_TTL_S == 60.0
    assert L2_TTL_S == 300.0


def test_put_then_get_hits_l2():
    c = TieredCache()
    c.put("a", {"v": 1})
    assert c.get("a") == {"v": 1}
    s = c.stats()
    assert s["hits"] == 1
    assert s["misses"] == 0
    assert s["l2_entries"] == 1


def test_miss_increments():
    c = TieredCache()
    assert c.get("missing") is None
    assert c.stats()["misses"] == 1


def test_l2_promotes_to_l1_after_two_hits():
    c = TieredCache()
    c.put("p", "val")
    assert c.get("p") == "val"  # hit 1 on L2
    assert c.stats()["l1_entries"] == 0
    assert c.get("p") == "val"  # hit 2 → promote
    assert c.stats()["l1_entries"] == 1
    assert c.get("p") == "val"  # L1 hit
    assert c.stats()["hits"] == 3


def test_invalidate_clears_both_tiers():
    c = TieredCache()
    c.put("x", 1)
    c.get("x")
    c.get("x")  # promote
    c.invalidate("x")
    assert c.get("x") is None
    assert c.stats()["l1_entries"] == 0
    assert c.stats()["l2_entries"] == 0


def test_l1_fifo_eviction():
    c = TieredCache()
    for i in range(L1_CAP + 2):
        k = f"k{i}"
        c.put(k, i)
        c.get(k)
        c.get(k)  # promote into L1
    assert c.stats()["l1_entries"] == L1_CAP
    # First two promotions should have been FIFO-evicted from L1.
    assert "k0" not in c._l1
    assert "k1" not in c._l1
    assert f"k{L1_CAP}" in c._l1
    assert f"k{L1_CAP + 1}" in c._l1


def test_l1_ttl_expiry(monkeypatch):
    c = TieredCache()
    c.put("t", "hot")
    c.get("t")
    c.get("t")  # in L1
    # Age the L1 entry past TTL
    with c._lock:
        c._l1["t"].inserted = time.monotonic() - (L1_TTL_S + 1)
    # L2 still warm — should hit L2 (and count as hit)
    assert c.get("t") == "hot"
