"""Adversarial regression tests for API middleware trust boundaries."""
from __future__ import annotations

import asyncio
from ipaddress import ip_network

from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from middleware import client_identity, security


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
    assert security._is_api_path("/api/health")
    assert not api_middleware._is_api_path("/apiary")
    assert not security._is_api_path("/apiary")
    assert not security._is_api_path("/apis")
    assert not security._is_api_path("/assets/api")


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
        first = await limiter.dispatch(_request(forwarded_for="127.0.0.1"), call_next)
        second = await limiter.dispatch(_request(forwarded_for="127.0.0.1"), call_next)
        return first.status_code, second.status_code

    first_status, second_status = asyncio.run(exercise())
    assert first_status == 200
    assert second_status == 429


def test_live_rate_limiter_uses_canonical_unspoofed_identity(monkeypatch):
    monkeypatch.setattr(client_identity, "TRUSTED_PROXY_NETWORKS", ())
    limiter = security.RateLimitMiddleware(
        app=lambda scope, receive, send: None,
        rps=1,
        burst=1,
        max_buckets=10,
    )
    ip, _route = limiter._key(_request(forwarded_for="127.0.0.1"))
    assert ip == "198.51.100.20"


def test_live_rate_limiter_whitelist_is_exact_not_prefix(monkeypatch):
    monkeypatch.setattr(client_identity, "TRUSTED_PROXY_NETWORKS", ())
    security.RateLimitMiddleware._buckets.clear()
    security.RateLimitMiddleware._lock = None
    limiter = security.RateLimitMiddleware(
        app=lambda scope, receive, send: None,
        rps=0,
        burst=1,
        max_buckets=10,
    )

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    async def exercise() -> tuple[int, int, int, int]:
        health_a = await limiter.dispatch(_request(path="/api/health"), call_next)
        health_b = await limiter.dispatch(_request(path="/api/health"), call_next)
        lookalike_a = await limiter.dispatch(_request(path="/api/healthcheck"), call_next)
        lookalike_b = await limiter.dispatch(_request(path="/api/healthcheck"), call_next)
        return (
            health_a.status_code,
            health_b.status_code,
            lookalike_a.status_code,
            lookalike_b.status_code,
        )

    assert asyncio.run(exercise()) == (200, 200, 200, 429)


def test_live_rate_limiter_bucket_state_is_bounded(monkeypatch):
    monkeypatch.setattr(client_identity, "TRUSTED_PROXY_NETWORKS", ())
    security.RateLimitMiddleware._buckets.clear()
    security.RateLimitMiddleware._lock = None
    limiter = security.RateLimitMiddleware(
        app=lambda scope, receive, send: None,
        rps=1,
        burst=1,
        max_buckets=2,
    )

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    async def exercise() -> None:
        for peer in ("198.51.100.1", "198.51.100.2", "198.51.100.3"):
            response = await limiter.dispatch(_request(peer=peer), call_next)
            assert response.status_code == 200

    asyncio.run(exercise())
    assert len(security.RateLimitMiddleware._buckets) == 2


def _asgi_scope(*, content_length: str | None = None) -> dict:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", content_length.encode("ascii")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/upload",
        "raw_path": b"/api/upload",
        "query_string": b"",
        "headers": headers,
        "client": ("198.51.100.20", 43123),
        "server": ("testserver", 80),
    }


def _run_size_limit(messages: list[dict], *, content_length: str | None = None):
    seen = bytearray()
    downstream_called = False
    sent = []

    async def downstream(scope, receive, send):
        nonlocal downstream_called
        downstream_called = True
        while True:
            message = await receive()
            if message["type"] == "http.request":
                seen.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break
        response = Response("ok", status_code=200)
        await response(scope, receive, send)

    middleware = security.SizeLimitMiddleware(downstream, max_mb=1)

    async def exercise():
        queue = list(messages)

        async def receive():
            if queue:
                return queue.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await middleware(_asgi_scope(content_length=content_length), receive, send)

    asyncio.run(exercise())
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    return status, downstream_called, bytes(seen)


def test_size_limit_rejects_malformed_content_length_before_application():
    status, called, _seen = _run_size_limit([], content_length="not-a-number")
    assert status == 400
    assert not called


def test_size_limit_rejects_chunked_body_without_content_length():
    messages = [
        {"type": "http.request", "body": b"a" * 700_000, "more_body": True},
        {"type": "http.request", "body": b"b" * 400_000, "more_body": False},
    ]
    status, called, _seen = _run_size_limit(messages)
    assert status == 413
    assert not called


def test_size_limit_rejects_body_larger_than_declared_length():
    messages = [
        {"type": "http.request", "body": b"a" * 700_000, "more_body": True},
        {"type": "http.request", "body": b"b" * 400_000, "more_body": False},
    ]
    status, called, _seen = _run_size_limit(messages, content_length="1")
    assert status == 413
    assert not called


def test_size_limit_replays_accepted_body_exactly():
    body = b"safe-body"
    status, called, seen = _run_size_limit(
        [{"type": "http.request", "body": body, "more_body": False}],
        content_length=str(len(body)),
    )
    assert status == 200
    assert called
    assert seen == body
