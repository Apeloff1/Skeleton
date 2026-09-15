"""Focused regressions that complete the API middleware security issue criteria."""

from __future__ import annotations

import asyncio
import ipaddress

from starlette.requests import Request

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
