from dataclasses import dataclass

import pytest

from core.runtime_resilience import CrashGuard, ErrorClass, ObjectPool, TtlLruCache


@dataclass
class Box:
    value: int = 0

    def reset(self):
        self.value = 0


def test_object_pool_reuses_and_resets_instances():
    pool = ObjectPool(Box, initial_size=1, max_size=2)
    box = pool.acquire()
    box.value = 9
    pool.release(box)
    reused = pool.acquire()
    assert reused is box
    assert reused.value == 0
    assert pool.stats()["active"] == 1


def test_object_pool_rejects_unbalanced_release():
    pool = ObjectPool(Box)
    with pytest.raises(RuntimeError, match="matching acquire"):
        pool.release(Box())


def test_ttl_lru_cache_expires_and_evicts_oldest():
    now = [0.0]
    cache = TtlLruCache[int](max_size=2, clock=lambda: now[0])
    cache.set("a", 1, ttl_seconds=5)
    cache.set("b", 2, ttl_seconds=5)
    assert cache.get("a") == 1
    cache.set("c", 3, ttl_seconds=5)
    assert cache.get("b") is None
    now[0] = 6
    assert cache.get("a") is None
    assert cache.clear_expired() == 1


def test_crash_guard_classifies_and_escalates_error_burst():
    now = [0.0]
    guard = CrashGuard(max_errors=3, window_seconds=10, clock=lambda: now[0])
    first = guard.handle("network fetch failed")
    assert first.error_class is ErrorClass.NETWORK
    assert first.recovery_action == "retry_with_backoff"
    guard.handle("audio context failed")
    third = guard.handle("webgl context lost")
    assert third.should_reset is True
    assert third.recovery_action == "full_reset"
    assert guard.status()["recovery_mode"] is True


def test_crash_guard_window_discards_old_errors():
    now = [0.0]
    guard = CrashGuard(max_errors=2, window_seconds=5, clock=lambda: now[0])
    guard.handle("render failed")
    now[0] = 10
    result = guard.handle("render failed")
    assert result.should_reset is False
    assert result.recent_error_count == 1
