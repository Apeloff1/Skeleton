from __future__ import annotations

import asyncio

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from api_middleware import (
    AccessLogMiddleware,
    OriginGuardMiddleware,
    RateLimiterMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)


async def _endpoint(_request):
    return JSONResponse({"ok": True})


def _stack(*, per_minute: int = 60, burst: int = 10):
    app = Starlette(routes=[Route("/api/private", _endpoint)])
    app = RateLimiterMiddleware(app, per_minute=per_minute, burst=burst, max_buckets=16)
    app = OriginGuardMiddleware(app)
    app = AccessLogMiddleware(app)
    app = SecurityHeadersMiddleware(app)
    app = RequestIdMiddleware(app)
    return app


def _request(app, *, origin: str | None = None, request_id: str | None = None):
    sent: list[dict] = []
    messages = [{"type": "http.request", "body": b"", "more_body": False}]

    headers = [(b"host", b"example.test")]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "scheme": "https",
        "path": "/api/private",
        "raw_path": b"/api/private",
        "query_string": b"",
        "headers": headers,
        "server": ("example.test", 443),
        "client": ("198.51.100.44", 53000),
    }

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], response_headers


def _assert_security_envelope(headers: dict[str, str]) -> None:
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["content-security-policy"].startswith("default-src 'none'")
    assert headers["strict-transport-security"].startswith("max-age=")
    assert headers["x-request-id"]


def test_origin_rejection_is_correlated_and_hardened(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    status, headers = _request(
        _stack(),
        origin="https://evil.example",
        request_id="bad\r\ninjected: yes",
    )
    assert status == 403
    _assert_security_envelope(headers)
    assert headers["x-request-id"] != "bad\r\ninjected: yes"
    assert "\r" not in headers["x-request-id"]
    assert "\n" not in headers["x-request-id"]


def test_rate_limit_rejection_is_correlated_and_hardened(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = _stack(per_minute=1, burst=1)

    first_status, first_headers = _request(app, request_id="first-safe-id")
    assert first_status == 200
    _assert_security_envelope(first_headers)

    second_status, second_headers = _request(app, request_id="second-safe-id")
    assert second_status == 429
    _assert_security_envelope(second_headers)
    assert second_headers["x-request-id"] == "second-safe-id"
