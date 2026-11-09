"""Adversarial regression coverage for the raw API request body boundary."""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from middleware.security import SizeLimitMiddleware


class _RecordingApp:
    def __init__(self) -> None:
        self.calls = 0
        self.bodies: list[bytes] = []

    async def __call__(self, scope, receive, send) -> None:
        self.calls += 1
        chunks: list[bytes] = []
        while True:
            message = await receive()
            assert message["type"] == "http.request"
            chunks.append(bytes(message.get("body") or b""))
            if not message.get("more_body", False):
                break
        self.bodies.append(b"".join(chunks))
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b""})


def _scope(
    *,
    path: str = "/api/test",
    headers: Iterable[tuple[bytes, bytes]] = (),
) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.5"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": list(headers),
        "client": ("192.0.2.10", 12345),
        "server": ("testserver", 80),
    }


async def _exercise(
    middleware: SizeLimitMiddleware,
    *,
    scope: dict,
    messages: Iterable[dict] = (),
) -> list[dict]:
    pending = list(messages)
    sent: list[dict] = []

    async def receive() -> dict:
        if not pending:
            raise AssertionError("request body was read unexpectedly")
        return pending.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    await middleware(scope, receive, send)
    return sent


def _status(sent: list[dict]) -> int:
    start = next(message for message in sent if message["type"] == "http.response.start")
    return int(start["status"])


def _json_body(sent: list[dict]) -> dict:
    payload = b"".join(
        bytes(message.get("body") or b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return json.loads(payload)


@pytest.mark.asyncio
async def test_declared_oversize_is_rejected_before_body_read() -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)
    limit = 1024 * 1024

    sent = await _exercise(
        middleware,
        scope=_scope(headers=[(b"content-length", str(limit + 1).encode("ascii"))]),
    )

    assert _status(sent) == 413
    assert _json_body(sent)["error"] == "payload_too_large"
    assert downstream.calls == 0
    assert middleware._inflight_body_bytes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"1"), (b"content-length", b"1")],
        [(b"transfer-encoding", b"chunked"), (b"transfer-encoding", b"chunked")],
        [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
    ],
)
async def test_ambiguous_request_framing_fails_closed(
    headers: list[tuple[bytes, bytes]],
) -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)

    sent = await _exercise(middleware, scope=_scope(headers=headers))

    assert _status(sent) == 400
    assert _json_body(sent) == {"error": "invalid_request_framing"}
    assert downstream.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [b"-1", b"+1", b"1.0", b"1e3", b"abc"])
async def test_invalid_content_length_is_rejected(value: bytes) -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)

    sent = await _exercise(
        middleware,
        scope=_scope(headers=[(b"content-length", value)]),
    )

    assert _status(sent) == 400
    assert _json_body(sent) == {"error": "invalid_content_length"}
    assert downstream.calls == 0


@pytest.mark.asyncio
async def test_streamed_body_over_limit_is_rejected_and_budget_released() -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)
    chunk = b"x" * (600 * 1024)

    sent = await _exercise(
        middleware,
        scope=_scope(headers=[(b"transfer-encoding", b"chunked")]),
        messages=[
            {"type": "http.request", "body": chunk, "more_body": True},
            {"type": "http.request", "body": chunk, "more_body": False},
        ],
    )

    assert _status(sent) == 413
    assert _json_body(sent)["error"] == "payload_too_large"
    assert downstream.calls == 0
    assert middleware._inflight_body_bytes == 0


@pytest.mark.asyncio
async def test_declared_length_must_match_streamed_body_exactly() -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)

    sent = await _exercise(
        middleware,
        scope=_scope(headers=[(b"content-length", b"4")]),
        messages=[{"type": "http.request", "body": b"abc", "more_body": False}],
    )

    assert _status(sent) == 400
    assert _json_body(sent) == {"error": "invalid_content_length"}
    assert downstream.calls == 0
    assert middleware._inflight_body_bytes == 0


@pytest.mark.asyncio
async def test_valid_api_body_is_replayed_verbatim_and_budget_released() -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)

    sent = await _exercise(
        middleware,
        scope=_scope(headers=[(b"content-length", b"6")]),
        messages=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ],
    )

    assert _status(sent) == 204
    assert downstream.calls == 1
    assert downstream.bodies == [b"abcdef"]
    assert middleware._inflight_body_bytes == 0


@pytest.mark.asyncio
async def test_api_prefix_lookalike_bypasses_api_body_policy() -> None:
    downstream = _RecordingApp()
    middleware = SizeLimitMiddleware(downstream, max_mb=1, max_inflight_mb=2)

    sent = await _exercise(
        middleware,
        scope=_scope(
            path="/apix",
            headers=[(b"content-length", str(2 * 1024 * 1024).encode("ascii"))],
        ),
        messages=[{"type": "http.request", "body": b"ok", "more_body": False}],
    )

    assert _status(sent) == 204
    assert downstream.calls == 1
    assert downstream.bodies == [b"ok"]
