"""Focused regression tests for bounded in-memory rate-limit state."""

import asyncio

import pytest

from api_middleware import (
    RateLimiterMiddleware,
    _bounded_retry_after,
    _is_api_path,
)


class _App:
    pass


def test_api_path_matching_requires_segment_boundary():
    assert _is_api_path("/api")
    assert _is_api_path("/api/run")
    assert _is_api_path("/api/run/deep")
    assert not _is_api_path("/apiary")
    assert not _is_api_path("/apis")
    assert not _is_api_path("/API/run")


@pytest.mark.asyncio
async def test_rate_limiter_prunes_expired_state_and_stays_bounded():
    limiter = RateLimiterMiddleware(_App(), per_minute=60, burst=1, max_buckets=3, bucket_ttl=300)

    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        async with limiter._get_state_lock():
            bucket, retry = limiter._bucket_for(ip)
            assert bucket is not None
            assert retry == 0.0

    oldest = limiter._buckets["10.0.0.1"]
    oldest.last -= 301

    async with limiter._get_state_lock():
        bucket, retry = limiter._bucket_for("10.0.0.4")

    assert bucket is not None
    assert retry == 0.0
    assert len(limiter._buckets) == 3
    assert "10.0.0.1" not in limiter._buckets
    assert "10.0.0.4" in limiter._buckets
    assert limiter._expired_pruned == 1


@pytest.mark.asyncio
async def test_rate_limiter_hard_cap_rejects_concurrent_high_cardinality_creation():
    limiter = RateLimiterMiddleware(_App(), per_minute=600, burst=1, max_buckets=8, bucket_ttl=300)
    admitted = 0
    rejected = 0

    async def add_bucket(i: int) -> None:
        nonlocal admitted, rejected
        async with limiter._get_state_lock():
            bucket, retry = limiter._bucket_for(f"192.0.2.{i}")
            if bucket is None:
                rejected += 1
                assert retry > 0
            else:
                admitted += 1
                assert retry == 0.0

    await asyncio.gather(*(add_bucket(i) for i in range(64)))

    assert len(limiter._buckets) == 8
    assert admitted == 8
    assert rejected == 56
    assert limiter._saturation_rejections == 56


@pytest.mark.asyncio
async def test_rate_limiter_preserves_active_bucket_when_capacity_is_full():
    limiter = RateLimiterMiddleware(_App(), per_minute=60, burst=2, max_buckets=2, bucket_ttl=300)

    async with limiter._get_state_lock():
        active, _ = limiter._bucket_for("198.51.100.1")
        other, _ = limiter._bucket_for("198.51.100.2")
        assert active is not None
        assert other is not None
        before = active.tokens
        ok, _ = active.take()
        assert ok
        assert active.tokens < before
        newcomer, retry = limiter._bucket_for("198.51.100.3")

    assert newcomer is None
    assert retry > 0
    assert len(limiter._buckets) == 2
    assert limiter._buckets["198.51.100.1"] is active
    assert limiter._buckets["198.51.100.2"] is other


@pytest.mark.asyncio
async def test_saturation_churn_cannot_reset_an_existing_exhausted_bucket():
    limiter = RateLimiterMiddleware(_App(), per_minute=1, burst=1, max_buckets=2, bucket_ttl=300)

    async with limiter._get_state_lock():
        tracked, _ = limiter._bucket_for("203.0.113.10")
        second, _ = limiter._bucket_for("203.0.113.11")
        assert tracked is not None
        assert second is not None
        ok, _ = tracked.take()
        assert ok
        tracked_identity = id(tracked)

    for i in range(100):
        async with limiter._get_state_lock():
            newcomer, retry = limiter._bucket_for(f"198.18.0.{i}")
            assert newcomer is None
            assert retry > 0

    async with limiter._get_state_lock():
        tracked_again, _ = limiter._bucket_for("203.0.113.10")
        assert tracked_again is not None
        assert id(tracked_again) == tracked_identity
        ok, retry = tracked_again.take()

    assert not ok
    assert retry > 0
    assert len(limiter._buckets) == 2
    assert limiter._saturation_rejections == 100


@pytest.mark.asyncio
async def test_expiry_reopens_capacity_without_active_eviction():
    limiter = RateLimiterMiddleware(_App(), per_minute=60, burst=1, max_buckets=2, bucket_ttl=30)

    async with limiter._get_state_lock():
        first, _ = limiter._bucket_for("10.1.0.1")
        second, _ = limiter._bucket_for("10.1.0.2")
        assert first is not None
        assert second is not None
        blocked, retry = limiter._bucket_for("10.1.0.3")
        assert blocked is None
        assert retry > 0
        first.last -= 31
        admitted, retry = limiter._bucket_for("10.1.0.3")

    assert admitted is not None
    assert retry == 0.0
    assert "10.1.0.1" not in limiter._buckets
    assert "10.1.0.2" in limiter._buckets
    assert "10.1.0.3" in limiter._buckets
    assert limiter._expired_pruned == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"per_minute": 0}, "per_minute must be finite and positive"),
        ({"per_minute": -1}, "per_minute must be finite and positive"),
        ({"per_minute": float("nan")}, "per_minute must be finite and positive"),
        ({"per_minute": float("inf")}, "per_minute must be finite and positive"),
        ({"burst": 0}, "burst must be finite and positive"),
        ({"burst": -1}, "burst must be finite and positive"),
        ({"burst": float("nan")}, "burst must be finite and positive"),
        ({"burst": float("inf")}, "burst must be finite and positive"),
        ({"max_buckets": 0}, "max_buckets must be positive"),
        ({"max_buckets": -1}, "max_buckets must be positive"),
        ({"bucket_ttl": 0}, "bucket_ttl must be finite and positive"),
        ({"bucket_ttl": -1}, "bucket_ttl must be finite and positive"),
        ({"bucket_ttl": float("nan")}, "bucket_ttl must be finite and positive"),
        ({"bucket_ttl": float("inf")}, "bucket_ttl must be finite and positive"),
    ],
)
def test_rate_limiter_rejects_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        RateLimiterMiddleware(_App(), **kwargs)


@pytest.mark.parametrize(
    ("retry", "expected"),
    [
        (0.0, 1),
        (0.1, 1),
        (1.2, 2),
        (86_399.1, 86_400),
        (90_000.0, 86_400),
        (float("inf"), 86_400),
        (float("nan"), 86_400),
    ],
)
def test_retry_after_is_finite_and_bounded(retry, expected):
    assert _bounded_retry_after(retry) == expected
