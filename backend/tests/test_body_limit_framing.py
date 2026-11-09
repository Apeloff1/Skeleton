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
    app_reads_body: bool = True,
) -> tuple[list[dict], bool]:
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

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, bounded_receive, bounded_send) -> None:
        nonlocal called
        called = True
        if app_reads_body:
            while True:
                message = await bounded_receive()
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

    asyncio.run(SizeLimitMiddleware(app, max_mb=1)(scope, receive, send))
    return sent, called


def test_duplicate_content_length_fails_closed_even_when_values_match() -> None:
    sent, called = _exercise(
        headers=[(b"content-length", b"1"), (b"content-length", b"1")],
        chunks=[b"x"],
    )

    assert _status(sent) == 400
    assert not called


def test_content_length_plus_transfer_encoding_fails_closed() -> None:
    sent, called = _exercise(
        headers=[(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
        chunks=[b"x"],
    )

    assert _status(sent) == 400
    assert not called


@pytest.mark.parametrize("bad", [b"+1", b"-1", b"1.0", b"0x10", b"1, 1"])
def test_non_decimal_content_length_forms_are_rejected(bad: bytes) -> None:
    sent, called = _exercise(headers=[(b"content-length", bad)], chunks=[b"x"])

    assert _status(sent) == 400
    assert not called


def test_declared_length_must_match_observed_body() -> None:
    sent, called = _exercise(
        headers=[(b"content-length", b"2")],
        chunks=[b"x"],
    )

    assert _status(sent) == 400
    assert not called


def test_streamed_body_without_content_length_is_capped_before_app() -> None:
    sent, called = _exercise(
        chunks=[b"a" * 700_000, b"b" * 400_000],
        app_reads_body=False,
    )

    assert _status(sent) == 413
    assert not called


def test_body_cap_applies_to_delete_not_only_write_verbs() -> None:
    sent, called = _exercise(
        method="DELETE",
        chunks=[b"a" * 1_048_577],
        app_reads_body=False,
    )

    assert _status(sent) == 413
    assert not called


def test_api_route_matching_does_not_capture_apiary_lookalike() -> None:
    sent, called = _exercise(
        path="/apiary/run",
        headers=[(b"content-length", b"999999999")],
        chunks=[b"x"],
    )

    assert _status(sent) == 204
    assert called


def test_oversized_declared_length_is_rejected_without_reading_body() -> None:
    sent, called = _exercise(
        headers=[(b"content-length", b"999999999999999999999999999999")],
        chunks=[b"x"],
        app_reads_body=False,
    )

    assert _status(sent) == 413
    assert not called


def test_inflight_body_budget_fails_closed_then_releases_capacity() -> None:
    async def scenario() -> None:
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        app_calls = 0

        async def app(scope, bounded_receive, bounded_send) -> None:
            nonlocal app_calls
            app_calls += 1
            while True:
                message = await bounded_receive()
                if not message.get("more_body", False):
                    break
            if app_calls == 1:
                first_entered.set()
                await release_first.wait()
            response = Response(status_code=204)
            await response(scope, bounded_receive, bounded_send)

        middleware = SizeLimitMiddleware(app, max_mb=1, max_inflight_mb=1)

        def exchange(body: bytes):
            queue = [{"type": "http.request", "body": body, "more_body": False}]
            sent: list[dict] = []

            async def receive() -> dict:
                return queue.pop(0)

            async def send(message: dict) -> None:
                sent.append(message)

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
            return scope, receive, send, sent

        first = exchange(b"a" * 700_000)
        first_task = asyncio.create_task(middleware(first[0], first[1], first[2]))
        await first_entered.wait()

        second = exchange(b"b" * 700_000)
        await middleware(second[0], second[1], second[2])
        assert _status(second[3]) == 503
        assert app_calls == 1

        release_first.set()
        await first_task
        assert _status(first[3]) == 204

        third = exchange(b"c" * 700_000)
        await middleware(third[0], third[1], third[2])
        assert _status(third[3]) == 204
        assert app_calls == 2

    asyncio.run(scenario())
