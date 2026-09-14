"""Regression coverage for request body and framing limits."""
from __future__ import annotations

import asyncio
import json

from middleware.security import SizeLimitMiddleware


async def _exercise(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    chunks: list[bytes] | None = None,
    method: str = "POST",
    path: str = "/api/upload",
):
    chunks = list(chunks or [b""])
    sent: list[dict] = []
    state = {"app_called": False, "body": b""}

    async def app(scope, receive, send):
        state["app_called"] = True
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        state["body"] = bytes(body)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    queue = []
    for index, chunk in enumerate(chunks):
        queue.append(
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
        )

    async def receive():
        if queue:
            return queue.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": ("198.51.100.10", 43210),
        "server": ("testserver", 80),
    }

    middleware = SizeLimitMiddleware(app, max_mb=1)
    await middleware(scope, receive, send)
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, body, state


def _run(**kwargs):
    return asyncio.run(_exercise(**kwargs))


def test_declared_oversized_body_is_rejected_before_application() -> None:
    status, body, state = _run(headers=[(b"content-length", str(1024 * 1024 + 1).encode("ascii"))])

    assert status == 413
    assert state["app_called"] is False
    payload = json.loads(body)
    assert payload["error"] == "payload_too_large"
    assert payload["limit_bytes"] == 1024 * 1024


def test_streamed_body_without_content_length_cannot_bypass_limit() -> None:
    status, body, state = _run(chunks=[b"a" * (700 * 1024), b"b" * (400 * 1024)])

    assert status == 413
    assert state["app_called"] is True
    assert state["body"] == b""
    payload = json.loads(body)
    assert payload["error"] == "payload_too_large"
    assert payload["got_bytes"] > payload["limit_bytes"]


def test_multichunk_body_within_limit_reaches_application_unchanged() -> None:
    chunks = [b"a" * (300 * 1024), b"b" * (400 * 1024), b"c" * 17]
    status, _body, state = _run(chunks=chunks)

    assert status == 204
    assert state["app_called"] is True
    assert state["body"] == b"".join(chunks)


def test_malformed_content_length_is_rejected() -> None:
    status, body, state = _run(headers=[(b"content-length", b"not-a-number")])

    assert status == 400
    assert state["app_called"] is False
    assert json.loads(body)["error"] == "invalid_content_length"


def test_negative_content_length_is_rejected() -> None:
    status, body, state = _run(headers=[(b"content-length", b"-1")])

    assert status == 400
    assert state["app_called"] is False
    assert json.loads(body)["error"] == "invalid_content_length"


def test_duplicate_content_length_is_rejected_as_ambiguous_framing() -> None:
    status, body, state = _run(
        headers=[(b"content-length", b"12"), (b"content-length", b"12")]
    )

    assert status == 400
    assert state["app_called"] is False
    assert json.loads(body)["error"] == "ambiguous_request_framing"


def test_content_length_plus_transfer_encoding_is_rejected() -> None:
    status, body, state = _run(
        headers=[(b"content-length", b"12"), (b"transfer-encoding", b"chunked")]
    )

    assert status == 400
    assert state["app_called"] is False
    assert json.loads(body)["error"] == "ambiguous_request_framing"
