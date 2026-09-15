"""Residual adversarial coverage for bounded rate-limit behavior."""

from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request
from starlette.responses import Response

from api_middleware import RateLimiterMiddleware, _bounded_retry_after


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.10", 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def _handler(_request: Request) -> Response:
    return Response(status_code=204)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"per_minute": float("nan")}, "per_minute must be finite and positive"),
        ({"per_minute": float("inf")}, "per_minute must be finite and positive"),
        ({"per_minute": True}, "per_minute must be finite and positive"),
        ({"burst": float("nan")}, "burst must be finite and positive"),
        ({"burst": float("inf")}, "burst must be finite and positive"),
        ({"burst": True}, "burst must be finite and positive"),
        ({"max_buckets": 1.5}, "max_buckets must be a positive integer"),
        ({"max_buckets": True}, "max_buckets must be a positive integer"),
    ],
)
def test_constructor_rejects_nonfinite_or_nondiscrete_limits(kwargs, message):
    with pytest.raises(ValueError, match=message):
        RateLimiterMiddleware(object(), **kwargs)


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
def test_retry_after_is_always_finite_and_bounded(retry, expected):
    assert _bounded_retry_after(retry) == expected


def test_activity_order_allows_expiry_without_full_table_scan_semantics():
    limiter = RateLimiterMiddleware(
        object(), per_minute=60, burst=2, max_buckets=3, bucket_ttl=30
    )

    first, _ = limiter._bucket_for("198.51.100.1")
    second, _ = limiter._bucket_for("198.51.100.2")
    third, _ = limiter._bucket_for("198.51.100.3")
    assert first is not None and second is not None and third is not None

    first_again, _ = limiter._bucket_for("198.51.100.1")
    assert first_again is first
    assert list(limiter._buckets) == [
        "198.51.100.2",
        "198.51.100.3",
        "198.51.100.1",
    ]

    second.last -= 31
    admitted, retry = limiter._bucket_for("198.51.100.4")
    assert admitted is not None
    assert retry == 0.0
    assert list(limiter._buckets) == [
        "198.51.100.3",
        "198.51.100.1",
        "198.51.100.4",
    ]
    assert limiter._expired_pruned == 1


def test_extreme_positive_rate_cannot_crash_retry_after_path():
    limiter = RateLimiterMiddleware(
        object(), per_minute=1e-320, burst=1, max_buckets=2, bucket_ttl=300
    )
    bucket, _ = limiter._bucket_for("192.0.2.10")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    response = asyncio.run(limiter.dispatch(_request(), _handler))
    payload = json.loads(response.body)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "86400"
    assert payload["retry_after_seconds"] == 86_400
