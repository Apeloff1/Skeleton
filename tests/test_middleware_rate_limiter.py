"""Reliability contracts for the API middleware token bucket."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

import skeleton.api.middleware as middleware
from skeleton.api.middleware import RateLimitError, RateLimiter


def test_rate_limiter_rejects_invalid_configuration():
    for capacity in (0, -1, float("nan"), float("inf"), True, False, "8"):
        with pytest.raises(ValueError):
            RateLimiter(capacity=capacity)

    for refill in (0, -1, float("nan"), float("inf"), True, False, "1"):
        with pytest.raises(ValueError):
            RateLimiter(refill_per_sec=refill)


def test_rate_limiter_rejects_invalid_token_costs():
    limiter = RateLimiter(capacity=2, refill_per_sec=1)

    for tokens in (0, -1, 3, float("nan"), float("inf"), True, False, "1"):
        with pytest.raises(ValueError):
            limiter.check("client", tokens=tokens)


def test_rate_limiter_refills_from_monotonic_time(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(middleware.time, "monotonic", lambda: clock[0])
    limiter = RateLimiter(capacity=2, refill_per_sec=1)

    limiter.check("client")
    limiter.check("client")
    with pytest.raises(RateLimitError):
        limiter.check("client")

    clock[0] = 101.0
    limiter.check("client")


def test_rate_limiter_reclaims_fully_refilled_idle_keys(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(middleware.time, "monotonic", lambda: clock[0])
    limiter = RateLimiter(capacity=1, refill_per_sec=1)

    for index in range(128):
        limiter.check(f"client-{index}")
    assert len(limiter._buckets) == 128

    clock[0] = 101.01
    limiter.check("fresh-client")

    assert set(limiter._buckets) == {"fresh-client"}


def test_rate_limiter_never_oversubscribes_under_contention(monkeypatch):
    monkeypatch.setattr(middleware.time, "monotonic", lambda: 100.0)
    limiter = RateLimiter(capacity=8, refill_per_sec=1)
    workers = 32
    barrier = Barrier(workers)

    def consume() -> bool:
        barrier.wait()
        try:
            limiter.check("shared-client")
        except RateLimitError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(workers)))

    assert sum(outcomes) == 8
    assert limiter._buckets["shared-client"][0] == 0
