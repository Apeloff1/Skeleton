from __future__ import annotations

import asyncio
import json

import pytest

from middleware.security import SizeLimitMiddleware


async def _drain_app(scope, receive, send):
    while True:
        message = await receive()
        if message.get("type") != "http.request" or not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _run(headers: list[tuple[bytes, bytes]], messages: list[dict], *, max_mb: int = 1):
    sent: list[dict] = []
    queue = list(messages)

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "scheme": "https",
        "path": "/api/upload",
        "raw_path": b"/api/upload",
        "query_string": b"",
        "headers": headers,
        "server": ("example.test", 443),
        "client": ("198.51.100.7", 53000),
    }
    middleware = SizeLimitMiddleware(_drain_app, max_mb=max_mb)
    asyncio.run(middleware(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return middleware, start["status"], json.loads(body or b"{}")


def test_duplicate_content_length_is_rejected_before_handler() -> None:
    _, status, payload = _run(
        [(b"content-length", b"4"), (b"content-length", b"4")],
        [{"type": "http.request", "body": b"test", "more_body": False}],
    )
    assert status == 400
    assert payload["error"] == "ambiguous_body_framing"


def test_content_length_plus_transfer_encoding_is_rejected() -> None:
    _, status, payload = _run(
        [(b"content-length", b"4"), (b"transfer-encoding", b"chunked")],
        [{"type": "http.request", "body": b"test", "more_body": False}],
    )
    assert status == 400
    assert payload["error"] == "ambiguous_body_framing"


@pytest.mark.parametrize("value", [b"-1", b"+1", b"1.0", b"1, 1", b"abc", b""])
def test_non_decimal_content_length_is_rejected(value: bytes) -> None:
    _, status, payload = _run(
        [(b"content-length", value)],
        [{"type": "http.request", "body": b"", "more_body": False}],
    )
    assert status == 400
    assert payload["error"] == "invalid_content_length"


def test_actual_body_cannot_exceed_declared_length() -> None:
    _, status, payload = _run(
        [(b"content-length", b"1")],
        [{"type": "http.request", "body": b"ab", "more_body": False}],
    )
    assert status == 413
    assert payload["error"] == "payload_too_large"


def test_pathological_chunk_count_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict] = []
    queue = [
        {"type": "http.request", "body": b"x", "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": False},
    ]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "scheme": "https",
        "path": "/api/upload",
        "raw_path": b"/api/upload",
        "query_string": b"",
        "headers": [],
        "server": ("example.test", 443),
        "client": ("198.51.100.7", 53000),
    }
    middleware = SizeLimitMiddleware(_drain_app, max_mb=1)
    middleware.max_chunks = 2
    asyncio.run(middleware(scope, receive, send))

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    assert start["status"] == 413
    assert json.loads(body)["error"] == "too_many_body_chunks"
