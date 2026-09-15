"""Adversarial regression tests for API middleware trust boundaries."""
from __future__ import annotations

import asyncio
from ipaddress import ip_network

from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from middleware import client_identity


def _request(
    path: str = "/api/example",
    *,
    peer: str = "198.51.100.20",
    forwarded_for: str | None = None,
) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43123),
            "server": ("testserver", 80),
        }
    )


def test_untrusted_peer_cannot_spoof_loopback_with_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(client_identity, "TRUSTED_PROXY_NETWORKS", ())
    request = _request(forwarded_for="127.0.0.1")

    assert api_middleware._client_ip(request) == "198.51.100.20"


def test_trusted_proxy_chain_resolves_first_untrusted_hop_from_the_right(monkeypatch):
    monkeypatch.setattr(
        client_identity,
        "TRUSTED_PROXY_NETWORKS",
        (ip_network("10.0.0.0/8"),),
    )
    request = _request(
        peer="10.0.0.2",
        forwarded_for="203.0.113.9, 10.0.0.3",
    )

    assert api_middleware._client_ip(request) == "203.0.113.9"


def test_malformed_forwarded_chain_fails_closed_to_immediate_peer(monkeypatch):
    monkeypatch.setattr(
        client_identity,
        "TRUSTED_PROXY_NETWORKS",
        (ip_network("10.0.0.0/8"),),
    )
    request = _request(
        peer="10.0.0.2",
        forwarded_for="203.0.113.9, definitely-not-an-ip",
    )

    assert api_middleware._client_ip(request) == "10.0.0.2"


def test_api_path_matcher_rejects_prefix_lookalikes():
    assert api_middleware._is_api_path("/api")
    assert api_middleware._is_api_path("/api/health")
    assert not api_middleware._is_api_path("/apiary")
    assert not api_middleware._is_api_path("/apis")
    assert not api_middleware._is_api_path("/assets/api")


def test_spoofed_exempt_forwarded_ip_does_not_bypass_rate_limit(monkeypatch):
    monkeypatch.setattr(client_identity, "TRUSTED_PROXY_NETWORKS", ())
    monkeypatch.setattr(api_middleware, "_EXEMPT_IPS", {"127.0.0.1"})
    limiter = api_middleware.RateLimiterMiddleware(
        app=lambda scope, receive, send: None,
        per_minute=1,
        burst=1,
    )

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    async def exercise() -> tuple[int, int]:
        first = await limiter.dispatch(
            _request(forwarded_for="127.0.0.1"),
            call_next,
        )
        second = await limiter.dispatch(
            _request(forwarded_for="127.0.0.1"),
            call_next,
        )
        return first.status_code, second.status_code

    first_status, second_status = asyncio.run(exercise())
    assert first_status == 200
    assert second_status == 429
