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
    assert c.get("p") == "val"
    assert c.stats()["l1_entries"] == 0
    assert c.get("p") == "val"
    assert c.stats()["l1_entries"] == 1
    assert c.get("p") == "val"
    assert c.stats()["hits"] == 3


def test_put_updates_already_hot_key_without_stale_l1_read():
    c = TieredCache()
    c.put("p", "old")
    c.get("p")
    c.get("p")
    assert c.get("p") == "old"

    c.put("p", "new")

    assert c.get("p") == "new"
    assert c._l1["p"].value == "new"
    assert c._l2["p"].value == "new"


def test_invalidate_clears_both_tiers():
    c = TieredCache()
    c.put("x", 1)
    c.get("x")
    c.get("x")
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
        c.get(k)
    assert c.stats()["l1_entries"] == L1_CAP
    assert "k0" not in c._l1
    assert "k1" not in c._l1
    assert f"k{L1_CAP}" in c._l1
    assert f"k{L1_CAP + 1}" in c._l1


def test_l1_ttl_expiry_falls_back_to_warm_tier():
    c = TieredCache()
    c.put("t", "hot")
    c.get("t")
    c.get("t")
    with c._lock:
        c._l1["t"].inserted = time.monotonic() - (L1_TTL_S + 1)
    assert c.get("t") == "hot"


def test_expired_entries_are_removed_on_access():
    c = TieredCache()
    c.put("expired", "value")
    c.get("expired")
    c.get("expired")
    with c._lock:
        c._l1["expired"].inserted = time.monotonic() - (L1_TTL_S + 1)
        c._l2["expired"].inserted = time.monotonic() - (L2_TTL_S + 1)

    assert c.get("expired") is None
    stats = c.stats()
    assert stats["l1_entries"] == 0
    assert stats["l2_entries"] == 0
    assert "expired" not in c._l1_order
    assert "expired" not in c._l2_order