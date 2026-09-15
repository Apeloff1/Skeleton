from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware.security import SizeLimitMiddleware  # noqa: E402


def _status(sent: list[dict]) -> int:
    return next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )


def _exercise(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    chunks: list[bytes] | None = None,
    method: str = "POST",
    path: str = "/api/run",
    max_mb: int = 1,
) -> tuple[list[dict], bool, bytes]:
    body_chunks = chunks if chunks is not None else [b""]
    queue = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(body_chunks) - 1,
        }
        for index, chunk in enumerate(body_chunks)
    ]
    sent: list[dict] = []
    called = False
    observed = bytearray()

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, bounded_receive, bounded_send) -> None:
        nonlocal called
        called = True
        while True:
            message = await bounded_receive()
            observed.extend(message.get("body") or b"")
            if not message.get("more_body", False):
                break
        response = Response(status_code=204)
        await response(scope, bounded_receive, bounded_send)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    asyncio.run(SizeLimitMiddleware(app, max_mb=max_mb)(scope, receive, send))
    return sent, called, bytes(observed)


def test_duplicate_content_length_fails_closed_even_if_equal() -> None:
    sent, called, _ = _exercise(
        headers=[(b"content-length", b"1"), (b"content-length", b"1")],
        chunks=[b"x"],
    )
    assert _status(sent) == 400
    assert not called


def test_duplicate_transfer_encoding_fails_closed() -> None:
    sent, called, _ = _exercise(
        headers=[
            (b"transfer-encoding", b"chunked"),
            (b"transfer-encoding", b"chunked"),
        ],
        chunks=[b"x"],
    )
    assert _status(sent) == 400
    assert not called


def test_content_length_plus_transfer_encoding_fails_closed() -> None:
    sent, called, _ = _exercise(
        headers=[(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
        chunks=[b"x"],
    )
    assert _status(sent) == 400
    assert not called


@pytest.mark.parametrize("bad", [b"+1", b"-1", b"1.0", b"0x10", b"1, 1", b"1  "])
def test_non_decimal_content_length_forms_are_rejected(bad: bytes) -> None:
    sent, called, _ = _exercise(headers=[(b"content-length", bad)], chunks=[b"x"])
    assert _status(sent) == 400
    assert not called


def test_absurd_content_length_text_is_rejected_without_integer_conversion() -> None:
    sent, called, _ = _exercise(
        headers=[(b"content-length", b"0" * 65)], chunks=[b""]
    )
    assert _status(sent) == 400
    assert not called


def test_declared_oversize_is_rejected_before_application() -> None:
    sent, called, _ = _exercise(
        headers=[(b"content-length", str(1024 * 1024 + 1).encode())],
        chunks=[b""],
    )
    assert _status(sent) == 413
    assert not called


def test_streamed_oversize_without_content_length_is_rejected() -> None:
    sent, called, _ = _exercise(chunks=[b"a" * 700_000, b"b" * 400_000])
    assert _status(sent) == 413
    assert not called


def test_declared_and_observed_length_mismatch_is_rejected() -> None:
    sent, called, _ = _exercise(
        headers=[(b"content-length", b"5")], chunks=[b"abc"]
    )
    assert _status(sent) == 400
    assert not called


def test_body_limit_applies_to_delete_requests() -> None:
    sent, called, _ = _exercise(
        method="DELETE", chunks=[b"a" * 700_000, b"b" * 400_000]
    )
    assert _status(sent) == 413
    assert not called


def test_apiary_lookalike_is_not_subject_to_api_body_policy() -> None:
    body = b"x" * (1024 * 1024 + 1)
    sent, called, observed = _exercise(path="/apiary", chunks=[body])
    assert _status(sent) == 204
    assert called
    assert observed == body


def test_within_limit_multichunk_body_is_replayed_verbatim() -> None:
    chunks = [b"hello", b"-", b"world"]
    sent, called, observed = _exercise(
        headers=[(b"content-length", b"11")], chunks=chunks
    )
    assert _status(sent) == 204
    assert called
    assert observed == b"hello-world"


def test_body_budget_is_released_after_downstream_failure() -> None:
    async def scenario() -> None:
        calls = 0

        async def app(scope, receive, send) -> None:
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        middleware = SizeLimitMiddleware(app, max_mb=1, max_inflight_mb=1)
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/run",
            "raw_path": b"/api/run",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        async def receive() -> dict:
            return {"type": "http.request", "body": b"x" * 128, "more_body": False}

        async def send(message: dict) -> None:
            pass

        with pytest.raises(RuntimeError):
            await middleware(scope, receive, send)
        assert calls == 1
        assert middleware._inflight_body_bytes == 0

    asyncio.run(scenario())
