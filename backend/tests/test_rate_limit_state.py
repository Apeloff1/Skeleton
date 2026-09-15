"""Regression coverage for bounded and concurrency-safe rate-limit state."""

import asyncio

from starlette.requests import Request
from starlette.responses import Response

from api_middleware import RateLimiterMiddleware, _Bucket, get_stats


def _request(ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [],
            "client": (ip, 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def _ok(_request: Request) -> Response:
    return Response(status_code=200)


def test_state_is_bounded_under_high_cardinality_traffic() -> None:
    middleware = RateLimiterMiddleware(
        object(), per_minute=60, burst=1, max_buckets=8, bucket_ttl=60
    )

    async def exercise() -> None:
        for index in range(100):
            response = await middleware.dispatch(_request(f"192.0.2.{index + 1}"), _ok)
            assert response.status_code == 200

    asyncio.run(exercise())

    assert len(middleware._buckets) == 8
    assert middleware._evictions == 92
    assert get_stats()["rate_limit"]["buckets"] == 8


def test_idle_buckets_are_pruned_before_new_state_is_added() -> None:
    middleware = RateLimiterMiddleware(
        object(), per_minute=60, burst=1, max_buckets=4, bucket_ttl=0.01
    )

    async def exercise() -> None:
        await middleware.dispatch(_request("192.0.2.10"), _ok)
        await asyncio.sleep(0.02)
        await middleware.dispatch(_request("192.0.2.11"), _ok)

    asyncio.run(exercise())

    assert set(middleware._buckets) == {"192.0.2.11"}
    assert middleware._evictions == 0


def test_concurrent_bucket_creation_never_exceeds_cap() -> None:
    middleware = RateLimiterMiddleware(
        object(), per_minute=60, burst=1, max_buckets=4, bucket_ttl=60
    )

    async def exercise() -> None:
        responses = await asyncio.gather(
            *(
                middleware.dispatch(_request(f"198.51.100.{index + 1}"), _ok)
                for index in range(64)
            )
        )
        assert all(response.status_code == 200 for response in responses)

    asyncio.run(exercise())

    assert len(middleware._buckets) == 4
    assert middleware._evictions == 60


def test_stale_bucket_detection_does_not_mutate_active_bucket() -> None:
    bucket = _Bucket(capacity=2, refill_per_sec=1)
    bucket.tokens = 0
    now = bucket.last + 10

    middleware = RateLimiterMiddleware(object(), max_buckets=4, bucket_ttl=5)
    middleware._buckets["198.51.100.20"] = bucket
    middleware._bucket_for("198.51.100.21", now=now)

    assert "198.51.100.20" not in middleware._buckets
    assert "198.51.100.21" in middleware._buckets
    assert bucket.tokens == 0
