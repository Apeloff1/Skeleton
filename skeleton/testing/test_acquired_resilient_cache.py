from __future__ import annotations

import pytest

from skeleton.acquired.resilient_cache import ResilientTTLCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_fresh_hit_avoids_loader():
    clock = Clock()
    cache = ResilientTTLCache[str, int](fresh_ttl=10, stale_ttl=30, clock=clock)
    cache.set("weather", 18)

    called = False

    def loader() -> int:
        nonlocal called
        called = True
        return 99

    result = cache.get_or_load("weather", loader)
    assert result.value == 18
    assert result.source == "fresh"
    assert called is False


def test_stale_value_is_served_only_when_loader_fails():
    clock = Clock()
    cache = ResilientTTLCache[str, str](fresh_ttl=5, stale_ttl=20, clock=clock)
    cache.set("signal", "cached")
    clock.now = 8

    def fail() -> str:
        raise RuntimeError("upstream down")

    result = cache.get_or_load("signal", fail)
    assert result.value == "cached"
    assert result.source == "stale"
    assert result.stale is True
    assert result.age_seconds == 8


def test_successful_refresh_replaces_stale_value():
    clock = Clock()
    cache = ResilientTTLCache[str, str](fresh_ttl=5, stale_ttl=20, clock=clock)
    cache.set("signal", "old")
    clock.now = 8

    result = cache.get_or_load("signal", lambda: "new")
    assert result.value == "new"
    assert result.source == "loaded"
    assert cache.get("signal").value == "new"


def test_expired_stale_value_does_not_hide_failure():
    clock = Clock()
    cache = ResilientTTLCache[str, str](fresh_ttl=5, stale_ttl=10, clock=clock)
    cache.set("signal", "old")
    clock.now = 11

    def fail() -> str:
        raise RuntimeError("still down")

    with pytest.raises(RuntimeError, match="still down"):
        cache.get_or_load("signal", fail)
    assert cache.stats()["entries"] == 0


def test_lru_capacity_is_bounded():
    clock = Clock()
    cache = ResilientTTLCache[str, int](fresh_ttl=10, stale_ttl=20, max_entries=2, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a").value == 1  # a is most recently used
    cache.set("c", 3)

    assert cache.get("a").value == 1
    assert cache.get("b") is None
    assert cache.get("c").value == 3
    assert cache.stats()["evictions"] == 1


def test_fatal_base_exceptions_are_never_converted_to_stale_hits():
    clock = Clock()
    cache = ResilientTTLCache[str, str](fresh_ttl=1, stale_ttl=20, clock=clock)
    cache.set("signal", "old")
    clock.now = 2

    def interrupt() -> str:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        cache.get_or_load("signal", interrupt)
    assert cache.stats()["stale_hits"] == 0


def test_invalid_resource_bounds_are_rejected():
    with pytest.raises(ValueError):
        ResilientTTLCache(max_entries=True)
    with pytest.raises(ValueError):
        ResilientTTLCache(fresh_ttl=True)
    with pytest.raises(ValueError):
        ResilientTTLCache(fresh_ttl=10, stale_ttl=9)
