from __future__ import annotations

import asyncio
import time

import api_middleware
from starlette.requests import Request
from starlette.responses import Response


def _request(peer: str) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/work",
        "raw_path": b"/api/work",
        "query_string": b"",
        "headers": [],
        "client": (peer, 43210),
        "server": ("testserver", 80),
    })


def _limiter(monkeypatch, *, max_buckets: int = 8, ttl: float = 900):
    monkeypatch.setattr(api_middleware, "_EXEMPT_IPS", set())
    monkeypatch.setattr(api_middleware, "_counts", {})

    async def app(scope, receive, send):
        return None

    return api_middleware.RateLimiterMiddleware(
        app, per_minute=60_000, burst=10, max_buckets=max_buckets, bucket_ttl=ttl
    )


def test_high_cardinality_state_is_bounded(monkeypatch):
    limiter = _limiter(monkeypatch, max_buckets=8)
    for index in range(200):
        limiter._bucket_for(f"client-{index}")
        assert len(limiter._buckets) <= 8
    assert len(limiter._buckets) == 8
    assert limiter._evictions >= 192


def test_idle_buckets_are_expired_and_counted(monkeypatch):
    limiter = _limiter(monkeypatch, max_buckets=16, ttl=1)
    stale = limiter._bucket_for("stale", now=10.0)
    active = limiter._bucket_for("active", now=10.5)
    assert stale is not active

    limiter._bucket_for("stale", now=12.0)

    assert "stale" in limiter._buckets
    assert "active" in limiter._buckets
    assert limiter._evictions == 1


def test_concurrent_dispatch_preserves_bucket_bound(monkeypatch):
    limiter = _limiter(monkeypatch, max_buckets=8)

    async def call_next(_request: Request) -> Response:
        return Response(status_code=204)

    async def exercise():
        return await asyncio.gather(*(
            limiter.dispatch(_request(f"198.51.100.{index + 1}"), call_next)
            for index in range(64)
        ))

    responses = asyncio.run(exercise())
    assert all(response.status_code == 204 for response in responses)
    assert len(limiter._buckets) <= 8
    assert limiter._evictions > 0


def test_reusing_bucket_does_not_create_duplicate_state(monkeypatch):
    limiter = _limiter(monkeypatch, max_buckets=8)
    first = limiter._bucket_for("same-client")
    second = limiter._bucket_for("same-client")
    assert first is second
    assert len(limiter._buckets) == 1
