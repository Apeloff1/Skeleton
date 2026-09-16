"""Regression tests for the HTTP request-header boundary guard."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("starlette")

from skeleton.api.request_bounds import HeaderBoundMiddleware, measure_headers


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _run(middleware: HeaderBoundMiddleware, scope: dict):
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(middleware(scope, _receive, send))
    return messages


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


def _body(messages):
    chunks = [m.get("body", b"") for m in messages if m["type"] == "http.response.body"]
    return json.loads(b"".join(chunks))


def test_measure_headers_counts_raw_asgi_bytes():
    headers = [(b"host", b"example.test"), (b"x-test", b"abc")]
    assert measure_headers(headers) == (2, 4 + 12 + 6 + 3)


def test_header_bounds_allows_request_within_limits():
    called = []

    async def app(scope, receive, send):
        called.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = HeaderBoundMiddleware(app, max_header_bytes=64, max_header_count=4)
    messages = _run(middleware, _scope([(b"host", b"test"), (b"x", b"ok")]))

    assert called == ["/health"]
    assert messages[0]["status"] == 204


def test_header_bounds_rejects_aggregate_bytes_before_app():
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


def test_header_bounds_rejects_header_count_before_app():
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


def test_header_bounds_environment_overrides_explicit_limits(monkeypatch):
    monkeypatch.setenv("SKELETON_GATE_MAX_HEADER_BYTES", "7")
    monkeypatch.setenv("SKELETON_GATE_MAX_HEADER_COUNT", "3")

    middleware = HeaderBoundMiddleware(lambda *_: None, max_header_bytes=99, max_header_count=99)

    assert middleware.max_header_bytes == 7
    assert middleware.max_header_count == 3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SKELETON_GATE_MAX_HEADER_BYTES", "0"),
        ("SKELETON_GATE_MAX_HEADER_COUNT", "-1"),
        ("SKELETON_GATE_MAX_HEADER_BYTES", "not-an-int"),
    ],
)
def test_header_bounds_rejects_invalid_configuration(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        HeaderBoundMiddleware(lambda *_: None)
