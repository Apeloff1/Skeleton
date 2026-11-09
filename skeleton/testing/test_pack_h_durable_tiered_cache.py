"""Pack H: DurableTieredCache read-through / write-behind over TieredCache."""

from __future__ import annotations

import threading
import time

import pytest

from skeleton.persistence.pack_h import DurableTier, DurableTieredCache, WriteBehindQueue


def _cache(**kw):
    tier = DurableTier()
    q = WriteBehindQueue(tier, batch_size=1000, flush_interval_s=3600)
    return DurableTieredCache(tier, write_behind=q, **kw), tier


def test_put_is_write_behind_and_get_reads_cache_first():
    c, tier = _cache()
    c.put("k", {"v": 1})
    assert c.get("k") == {"v": 1}
    assert tier.get("k") is None
    c.flush()
    assert tier.get("k") == {"v": 1}


def test_read_through_backfills_from_durable():
    c, tier = _cache()
    tier.put("k", "durable")
    assert c.get("k") == "durable"
    assert c.stats()["read_through_hits"] == 1
    tier.put("k", "changed-underneath")
    assert c.get("k") == "durable"  # served from L1/L2 now
    c.evict_local("k")
    assert c.get("k") == "changed-underneath"


def test_invalidate_tombstones_durable_and_does_not_resurrect():
    c, tier = _cache()
    c.put("k", "v", durable_sync=True)
    assert tier.get("k") == "v"
    c.invalidate("k")
    assert c.get("k") is None  # pending delete wins over durable row
    c.flush()
    assert tier.get("k") is None
    assert c.get("k") is None


def test_pending_write_visible_after_local_eviction():
    c, tier = _cache()
    c.put("k", "pending")
    c.evict_local("k")
    assert c.get("k") == "pending"
    assert c.stats()["pending_hits"] == 1


def test_durable_sync_flushes_older_queued_write_first():
    c, tier = _cache()
    c.put("k", "old")
    c.put("k", "new", durable_sync=True)
    c.flush()
    assert tier.get("k") == "new"


def test_none_is_rejected():
    c, _ = _cache()
    with pytest.raises(ValueError):
        c.put("k", None)


def test_get_or_load_single_flight():
    c, _ = _cache()
    calls = []
    gate = threading.Event()

    def loader():
        calls.append(1)
        gate.wait(2)
        return "loaded"

    results = []
    threads = [threading.Thread(target=lambda: results.append(c.get_or_load("k", loader))) for _ in range(6)]
    [t.start() for t in threads]
    time.sleep(0.05)
    gate.set()
    [t.join() for t in threads]
    assert results == ["loaded"] * 6
    assert len(calls) == 1


def test_get_or_load_propagates_error_and_allows_retry():
    c, _ = _cache()

    def boom():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        c.get_or_load("k", boom)
    assert c.get_or_load("k", lambda: 5) == 5


def test_write_behind_must_share_tier():
    with pytest.raises(ValueError):
        DurableTieredCache(DurableTier(), write_behind=WriteBehindQueue(DurableTier()))


def test_close_flushes():
    c, tier = _cache()
    c.put("k", 1)
    c.close()
    assert tier.get("k") == 1
