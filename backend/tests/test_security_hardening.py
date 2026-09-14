from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response

from api_middleware import RateLimiterMiddleware
from middleware.client_identity import (
    extract_client_ip,
    parse_trusted_proxy_cidrs,
    sanitize_request_id,
)
from middleware.security import AuditMiddleware, SizeLimitMiddleware, safe_relative_path


def test_proxy_trust_is_fail_closed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    assert parse_trusted_proxy_cidrs() == ()
    assert extract_client_ip("127.0.0.1", "203.0.113.99") == "127.0.0.1"


def test_untrusted_peer_cannot_spoof_forwarded_for() -> None:
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert extract_client_ip("198.51.100.7", "203.0.113.99", trusted) == "198.51.100.7"


def test_trusted_proxy_chain_selects_nearest_untrusted_client() -> None:
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert (
        extract_client_ip(
            "10.0.0.10",
            "203.0.113.7, 10.0.0.20",
            trusted,
        )
        == "203.0.113.7"
    )


def test_malformed_forwarded_hops_never_become_identity() -> None:
    trusted = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert extract_client_ip("10.0.0.10", "not-an-ip, also-bad", trusted) == "10.0.0.10"


def test_request_id_is_bounded_and_printable() -> None:
    safe = "trace-1234.abcd:01"
    assert sanitize_request_id(safe) == safe

    for unsafe in ("", "x" * 65, "bad\nheader", "space is not allowed"):
        generated = sanitize_request_id(unsafe)
        assert generated != unsafe
        assert len(generated) == 32
        assert generated.isalnum()


def test_rate_limiter_bucket_cache_is_bounded_lru() -> None:
    middleware = RateLimiterMiddleware(lambda scope, receive, send: None, max_buckets=2)
    middleware._bucket_for("192.0.2.1")
    middleware._bucket_for("192.0.2.2")
    middleware._bucket_for("192.0.2.3")

    assert len(middleware._buckets) == 2
    assert "192.0.2.1" not in middleware._buckets
    assert set(middleware._buckets) == {"192.0.2.2", "192.0.2.3"}


def test_unknown_client_does_not_bypass_rate_limit() -> None:
    middleware = RateLimiterMiddleware(
        lambda scope, receive, send: None,
        per_minute=1,
        burst=1,
        max_buckets=4,
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "scheme": "https",
        "path": "/api/private",
        "raw_path": b"/api/private",
        "query_string": b"",
        "headers": [],
        "server": ("example.test", 443),
    }
    request = Request(scope)

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    first = asyncio.run(middleware.dispatch(request, call_next))
    second = asyncio.run(middleware.dispatch(Request(scope), call_next))

    assert first.status_code == 200
    assert second.status_code == 429
    assert "unknown" in middleware._buckets


def test_loopback_client_is_not_implicitly_exempt() -> None:
    middleware = RateLimiterMiddleware(
        lambda scope, receive, send: None,
        per_minute=1,
        burst=1,
        max_buckets=4,
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "scheme": "http",
        "path": "/api/private",
        "raw_path": b"/api/private",
        "query_string": b"",
        "headers": [],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 53000),
    }

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    first = asyncio.run(middleware.dispatch(Request(scope), call_next))
    second = asyncio.run(middleware.dispatch(Request(scope), call_next))

    assert first.status_code == 200
    assert second.status_code == 429


def test_audit_snapshot_redacts_client_metadata_by_default() -> None:
    original = AuditMiddleware._buf
    try:
        from collections import deque

        AuditMiddleware._buf = deque(
            [
                {
                    "ts": 1.0,
                    "method": "GET",
                    "path": "/api/private",
                    "status": 200,
                    "duration_ms": 1.2,
                    "ip": "203.0.113.10",
                    "ua": "sensitive-user-agent",
                    "rid": "abc123",
                    "req_bytes": 0,
                    "error": None,
                }
            ],
            maxlen=5000,
        )
        public = AuditMiddleware.snapshot()
        assert "ip" not in public["entries"][0]
        assert "ua" not in public["entries"][0]

        privileged = AuditMiddleware.snapshot(include_sensitive=True)
        assert privileged["entries"][0]["ip"] == "203.0.113.10"
    finally:
        AuditMiddleware._buf = original


def test_audit_middleware_applies_security_header_baseline() -> None:
    middleware = AuditMiddleware(lambda scope, receive, send: None)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "scheme": "https",
        "path": "/api/private",
        "raw_path": b"/api/private",
        "query_string": b"",
        "headers": [],
        "server": ("example.test", 443),
        "client": ("198.51.100.7", 53000),
    }

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    response = asyncio.run(middleware.dispatch(Request(scope), call_next))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["strict-transport-security"].startswith("max-age=")
    assert response.headers["referrer-policy"] == "no-referrer"


def test_safe_relative_path_rejects_escape_and_absolute_paths(tmp_path: Path) -> None:
    base = tmp_path / "uploads"
    base.mkdir()

    assert safe_relative_path(base, "nested/file.txt") == (base / "nested/file.txt").resolve()

    for unsafe in ("../secret.txt", "/etc/passwd", "C:\\Windows\\system.ini", "\\\\server\\share", "bad\x00name"):
        with pytest.raises(ValueError, match="unsafe path"):
            safe_relative_path(base, unsafe)


def test_size_limit_enforces_streamed_body_without_content_length() -> None:
    sent: list[dict] = []
    messages = [
        {"type": "http.request", "body": b"x" * (1024 * 1024 + 1), "more_body": False},
    ]

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    middleware = SizeLimitMiddleware(app, max_mb=1)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/upload",
        "headers": [],
    }
    asyncio.run(middleware(scope, receive, send))

    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert starts
    assert starts[0]["status"] == 413
