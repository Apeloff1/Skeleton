"""Regression tests for the standalone request-header boundary guard."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("starlette")

from skeleton.api.request_bounds import HeaderBoundMiddleware, measure_headers


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _scope(headers):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }


def _run(middleware, scope):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(middleware(scope, _receive, send))
    return messages


def _body(messages):
    chunks = [
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ]
    return json.loads(b"".join(chunks))


def test_measure_headers_counts_raw_asgi_bytes():
    headers = [(b"host", b"example.test"), (b"x-test", b"abc")]
    assert measure_headers(headers) == (2, 4 + 12 + 6 + 3)


def test_allows_request_within_limits():
    called = []

    async def app(scope, receive, send):
        called.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = HeaderBoundMiddleware(app, max_header_bytes=64, max_header_count=4)
    messages = _run(middleware, _scope([(b"host", b"test"), (b"x", b"ok")]))

    assert called == ["/health"]
    assert messages[0]["status"] == 204


def test_rejects_aggregate_bytes_before_app():
    called = []

    async def app(scope, receive, send):
        called.append(True)

    middleware = HeaderBoundMiddleware(app, max_header_bytes=8, max_header_count=10)
    messages = _run(middleware, _scope([(b"x", b"12345678")]))

    assert called == []
    assert messages[0]["status"] == 431
    assert _body(messages) == {
        "error": "request_headers_too_large",
        "reason": "header_bytes",
        "limit_bytes": 8,
        "limit_count": 10,
    }


def test_rejects_header_count_before_app():
    called = []

    async def app(scope, receive, send):
        called.append(True)

    middleware = HeaderBoundMiddleware(app, max_header_bytes=1024, max_header_count=2)
    messages = _run(
        middleware,
        _scope([(b"a", b"1"), (b"b", b"2"), (b"c", b"3")]),
    )

    assert called == []
    assert messages[0]["status"] == 431
    assert _body(messages)["reason"] == "header_count"


def test_environment_limits_override_constructor_values(monkeypatch):
    monkeypatch.setenv("SKELETON_GATE_MAX_HEADER_BYTES", "8")
    monkeypatch.setenv("SKELETON_GATE_MAX_HEADER_COUNT", "1")

    async def app(scope, receive, send):
        return None

    middleware = HeaderBoundMiddleware(app, max_header_bytes=1024, max_header_count=10)

    assert middleware.max_header_bytes == 8
    assert middleware.max_header_count == 1


def test_limits_must_be_positive():
    async def app(scope, receive, send):
        return None

    with pytest.raises(ValueError, match="must be positive"):
        HeaderBoundMiddleware(app, max_header_bytes=0)
    with pytest.raises(ValueError, match="must be positive"):
        HeaderBoundMiddleware(app, max_header_count=-1)


def test_non_http_scope_passes_through():
    called = []

    async def app(scope, receive, send):
        called.append(scope["type"])

    middleware = HeaderBoundMiddleware(app, max_header_bytes=1, max_header_count=1)
    _run(middleware, {"type": "lifespan"})

    assert called == ["lifespan"]
