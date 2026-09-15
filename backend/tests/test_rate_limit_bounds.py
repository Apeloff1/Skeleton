"""Focused regression tests for bounded in-memory rate-limit state."""

import asyncio

import pytest

from api_middleware import RateLimiterMiddleware


class _App:
    pass


@pytest.mark.asyncio
async def test_rate_limiter_evicts_stale_state_and_stays_bounded():
    limiter = RateLimiterMiddleware(_App(), per_minute=60, burst=1, max_buckets=3, bucket_ttl=300)

    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        async with limiter._get_state_lock():
            limiter._bucket_for(ip)

    assert len(limiter._buckets) == 3

    oldest = limiter._buckets["10.0.0.1"]
    oldest.last -= 301

    async with limiter._get_state_lock():
        limiter._bucket_for("10.0.0.4")

    assert len(limiter._buckets) == 3
    assert "10.0.0.1" not in limiter._buckets
    assert "10.0.0.4" in limiter._buckets


@pytest.mark.asyncio
async def test_rate_limiter_hard_cap_survives_concurrent_high_cardinality_creation():
    limiter = RateLimiterMiddleware(_App(), per_minute=600, burst=1, max_buckets=8, bucket_ttl=300)

    async def add_bucket(i: int) -> None:
        async with limiter._get_state_lock():
            limiter._bucket_for(f"192.0.2.{i}")

    await asyncio.gather(*(add_bucket(i) for i in range(64)))

    assert len(limiter._buckets) == 8
    assert limiter._evictions == 56


@pytest.mark.asyncio
async def test_rate_limiter_keeps_active_bucket_and_reports_state_metrics():
    limiter = RateLimiterMiddleware(_App(), per_minute=60, burst=2, max_buckets=2, bucket_ttl=300)

    async with limiter._get_state_lock():
        active = limiter._bucket_for("198.51.100.1")
        limiter._bucket_for("198.51.100.2")

    before = active.tokens
    ok, _ = active.take()

    assert ok
    assert active.tokens < before
    assert len(limiter._buckets) == 2

    # A third identity cannot grow the map beyond the configured cap.
    async with limiter._get_state_lock():
        limiter._bucket_for("198.51.100.3")
    assert len(limiter._buckets) == 2
