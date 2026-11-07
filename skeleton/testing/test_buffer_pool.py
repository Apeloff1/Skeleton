"""Tests for skeleton.kernel.buffer_pool (gameforge-rs buffers::BufferPool port)."""

from __future__ import annotations

import threading

from skeleton.kernel.buffer_pool import (
    CLASS_CAP,
    CLASS_LARGE,
    CLASS_MEDIUM,
    CLASS_SMALL,
    BufferPool,
    Class,
    Lease,
)


def test_class_sizes_match_rs():
    assert CLASS_SMALL == 4096
    assert CLASS_MEDIUM == 65536
    assert CLASS_LARGE == 1 << 20
    assert CLASS_CAP == 64
    assert Class.SMALL.value == 4096
    assert Class.MEDIUM.value == 65536
    assert Class.LARGE.value == 1 << 20


def test_lease_picks_class_by_min_size():
    pool = BufferPool()
    small = pool.lease(1)
    medium = pool.lease(4097)
    large = pool.lease(65537)
    assert small.size_class is Class.SMALL
    assert medium.size_class is Class.MEDIUM
    assert large.size_class is Class.LARGE
    assert len(small.buf) >= CLASS_SMALL
    assert len(medium.buf) >= CLASS_MEDIUM
    assert len(large.buf) >= CLASS_LARGE
    assert pool.leased == 3
    small.release()
    medium.release()
    large.release()
    assert pool.leased == 0


def test_lease_boundary_sizes():
    pool = BufferPool()
    a = pool.lease(4096)
    b = pool.lease(65536)
    c = pool.lease(1 << 20)
    assert a.size_class is Class.SMALL
    assert b.size_class is Class.MEDIUM
    assert c.size_class is Class.LARGE
    a.release()
    b.release()
    c.release()


def test_context_manager_reclaims():
    pool = BufferPool()
    with pool.lease(16) as lease:
        assert isinstance(lease, Lease)
        assert pool.leased == 1
        lease.buf[0] = 7
    assert pool.leased == 0
    stats = pool.stats()
    assert stats["leased"] == 0
    assert stats["small"] == 1


def test_release_is_idempotent():
    pool = BufferPool()
    lease = pool.lease(8)
    lease.release()
    lease.release()
    assert pool.leased == 0
    assert pool.stats()["small"] == 1


def test_reclaim_reuses_buffer():
    pool = BufferPool()
    first = pool.lease(32)
    identity = id(first.buf)
    first.release()
    second = pool.lease(32)
    assert id(second.buf) == identity
    second.release()


def test_class_cap_drops_overflow():
    pool = BufferPool()
    leases = [pool.lease(1) for _ in range(CLASS_CAP + 8)]
    assert pool.leased == CLASS_CAP + 8
    for lease in leases:
        lease.release()
    assert pool.leased == 0
    assert pool.stats()["small"] == CLASS_CAP
    assert pool.stats()["class_cap"] == CLASS_CAP


def test_stats_counters():
    pool = BufferPool()
    assert pool.stats() == {
        "leased": 0,
        "small": 0,
        "medium": 0,
        "large": 0,
        "class_cap": CLASS_CAP,
    }
    held = [pool.lease(1), pool.lease(5000), pool.lease(70000)]
    s = pool.stats()
    assert s["leased"] == 3
    assert s["small"] == 0
    for lease in held:
        lease.release()
    s = pool.stats()
    assert s["leased"] == 0
    assert s["small"] == 1
    assert s["medium"] == 1
    assert s["large"] == 1


def test_concurrent_lease_and_release():
    pool = BufferPool()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(40):
                with pool.lease(128) as lease:
                    lease.buf[0] = 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert pool.leased == 0
    assert pool.stats()["small"] <= CLASS_CAP
