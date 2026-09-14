"""Stress/regression tests for bounded in-memory rate-limit state."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import api_middleware
from starlette.requests import Request
from starlette.responses import Response


def _request(peer: str) -> Request:
    return Request(
        {
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
        }
    )


def _isolated_limiter(monkeypatch, *, max_buckets: int = 8, ttl: int = 900):
    monkeypatch.setattr(api_middleware, "_RATE_MAX_BUCKETS", max_buckets)
    monkeypatch.setattr(api_middleware, "_RATE_BUCKET_TTL", ttl)
    monkeypatch.setattr(api_middleware, "_EXEMPT_IPS", set())
    monkeypatch.setattr(api_middleware, "_counts", defaultdict(int))

    async def app(scope, receive, send):
        return None

    return api_middleware.RateLimiterMiddleware(app, per_minute=60_000, burst=10)


def test_high_cardinality_bucket_state_remains_bounded(monkeypatch) -> None:
    limiter = _isolated_limiter(monkeypatch, max_buckets=8)

    for index in range(200):
        limiter._bucket_for(f"client-{index}")
        assert len(limiter._buckets) <= 8

    stats = api_middleware.get_stats()["rate_limit"]
    assert stats["active_buckets"] == len(limiter._buckets) <= 8
    assert stats["evictions_total"] >= 192


def test_stale_bucket_pruning_updates_eviction_telemetry(monkeypatch) -> None:
    limiter = _isolated_limiter(monkeypatch, max_buckets=16, ttl=1)
    stale = limiter._bucket_for("stale-client")
    limiter._bucket_for("active-client")

    now = time.monotonic()
    stale.last = now - 10
    limiter._last_prune = 0
    limiter._prune_buckets(now)

    assert "stale-client" not in limiter._buckets
    assert "active-client" in limiter._buckets
    stats = api_middleware.get_stats()["rate_limit"]
    assert stats["active_buckets"] == 1
    assert stats["evictions_total"] == 1


def test_concurrent_requests_do_not_break_bucket_bound(monkeypatch) -> None:
    limiter = _isolated_limiter(monkeypatch, max_buckets=8)

    async def call_next(_request: Request) -> Response:
        await asyncio.sleep(0)
        return Response(status_code=204)

    async def exercise() -> list[Response]:
        return await asyncio.gather(
            *(
                limiter.dispatch(_request(f"198.51.100.{index + 1}"), call_next)
                for index in range(64)
            )
        )

    responses = asyncio.run(exercise())

    assert all(response.status_code == 204 for response in responses)
    assert len(limiter._buckets) <= 8
    stats = api_middleware.get_stats()["rate_limit"]
    assert stats["active_buckets"] <= 8
    assert stats["evictions_total"] > 0


def test_bucket_reuse_does_not_inflate_active_count(monkeypatch) -> None:
    limiter = _isolated_limiter(monkeypatch, max_buckets=8)

    first = limiter._bucket_for("same-client")
    second = limiter._bucket_for("same-client")

    assert first is second
    stats = api_middleware.get_stats()["rate_limit"]
    assert stats["active_buckets"] == 1
    assert stats["evictions_total"] == 0
