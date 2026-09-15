"""Focused regressions that complete the API middleware security issue criteria."""

from __future__ import annotations

import asyncio
import ipaddress
import json

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import RateLimiterMiddleware


def _request(client_host: str, *, xff: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", xff.encode("latin-1"))],
            "client": (client_host, 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def _plain_request(client_host: str = "192.0.2.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [],
            "client": (client_host, 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def _admit(limiter: RateLimiterMiddleware, identity: str):
    async def exercise():
        async with limiter._get_state_lock():
            return limiter._bucket_for(identity)

    return asyncio.run(exercise())


def test_untrusted_peer_cannot_rotate_identity_by_changing_xff(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    first = _request("198.51.100.20", xff="203.0.113.10")
    rotated = _request("198.51.100.20", xff="192.0.2.77")

    assert api_middleware._client_ip(first) == "198.51.100.20"
    assert api_middleware._client_ip(rotated) == "198.51.100.20"


def test_trusted_ipv6_proxy_chain_resolves_nearest_untrusted_hop(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("2001:db8:ffff::/48"),),
    )
    request = _request(
        "2001:db8:ffff::10",
        xff="2001:db8:1::5, 2001:db8:ffff::20",
    )

    assert api_middleware._client_ip(request) == "2001:db8:1::5"


def test_expiry_pruning_preserves_active_bucket_state_and_reports_metrics() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=60, burst=2, max_buckets=3, bucket_ttl=300
    )
    for identity in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        bucket, retry = _admit(limiter, identity)
        assert bucket is not None
        assert retry == 0.0

    active = limiter._buckets["10.0.0.2"]
    consumed, _ = active.take()
    assert consumed
    active_identity = id(active)
    active_tokens = active.tokens

    limiter._buckets["10.0.0.1"].last -= 301
    replacement, retry = _admit(limiter, "10.0.0.4")

    assert replacement is not None
    assert retry == 0.0
    assert len(limiter._buckets) == 3
    assert "10.0.0.1" not in limiter._buckets
    assert id(limiter._buckets["10.0.0.2"]) == active_identity
    assert limiter._buckets["10.0.0.2"].tokens == active_tokens

    stats = api_middleware.get_stats()["rate_limit"]
    assert stats["buckets"] == 3
    assert stats["evictions"] >= 1
    assert stats["expired_pruned"] >= 1


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
    assert api_middleware._bounded_retry_after(retry) == expected


def test_recent_activity_reorders_bucket_before_expiry_pruning() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=60, burst=2, max_buckets=3, bucket_ttl=30
    )
    first, _ = _admit(limiter, "198.51.100.1")
    second, _ = _admit(limiter, "198.51.100.2")
    third, _ = _admit(limiter, "198.51.100.3")
    assert first is not None and second is not None and third is not None

    first_again, _ = _admit(limiter, "198.51.100.1")
    assert first_again is first
    assert list(limiter._buckets) == [
        "198.51.100.2",
        "198.51.100.3",
        "198.51.100.1",
    ]

    second.last -= 31
    admitted, retry = _admit(limiter, "198.51.100.4")
    assert admitted is not None
    assert retry == 0.0
    assert list(limiter._buckets) == [
        "198.51.100.3",
        "198.51.100.1",
        "198.51.100.4",
    ]
    assert limiter._expired_pruned == 1


def test_extreme_positive_rate_cannot_crash_retry_after_path() -> None:
    limiter = RateLimiterMiddleware(
        object(), per_minute=1e-320, burst=1, max_buckets=2, bucket_ttl=300
    )
    bucket, _ = _admit(limiter, "192.0.2.10")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    async def handler(_request: Request) -> Response:
        return Response(status_code=204)

    response = asyncio.run(limiter.dispatch(_plain_request(), handler))
    payload = json.loads(response.body)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "86400"
    assert payload["retry_after_seconds"] == 86_400
