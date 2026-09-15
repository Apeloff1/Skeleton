from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware.security import (  # noqa: E402
    RateLimitMiddleware,
    SizeLimitMiddleware,
    _request_client_ip,
)


def _request(*, peer: str, xff: str | None = None) -> Request:
    headers = [] if xff is None else [(b"x-forwarded-for", xff.encode("ascii"))]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/run",
            "raw_path": b"/api/run",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 12345),
            "server": ("testserver", 80),
        }
    )


def test_direct_client_cannot_spoof_forwarded_identity_when_proxy_trust_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(peer="198.51.100.7", xff="127.0.0.1")

    assert _request_client_ip(request) == "198.51.100.7"


def test_trusted_proxy_chain_resolves_nearest_untrusted_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        peer="10.0.0.2",
        xff="203.0.113.9, 198.51.100.8, 10.0.0.3",
    )

    assert _request_client_ip(request) == "198.51.100.8"


def test_malformed_forwarded_chain_fails_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(peer="10.0.0.2", xff="203.0.113.9, definitely-not-an-ip")

    assert _request_client_ip(request) == "10.0.0.2"


def test_malformed_trusted_proxy_configuration_disables_forwarded_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,not-a-cidr")
    request = _request(peer="10.0.0.2", xff="203.0.113.9")

    assert _request_client_ip(request) == "10.0.0.2"


def test_rate_limit_eviction_is_lru_not_linear_oldest_scan() -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        RateLimitMiddleware._buckets.clear()
        RateLimitMiddleware._lock = asyncio.Lock()
        middleware = RateLimitMiddleware(app, rps=1, burst=3, max_buckets=2)

        first = _request(peer="198.51.100.1")
        second = _request(peer="198.51.100.2")
        third = _request(peer="198.51.100.3")
        await middleware.dispatch(first, call_next)
        await middleware.dispatch(second, call_next)
        await middleware.dispatch(first, call_next)
        await middleware.dispatch(third, call_next)

        keys = list(RateLimitMiddleware._buckets)
        assert any(key[0] == "198.51.100.1" for key in keys)
        assert any(key[0] == "198.51.100.3" for key in keys)
        assert not any(key[0] == "198.51.100.2" for key in keys)

    asyncio.run(scenario())


def _exercise(
    *,
    headers: list[tuple[bytes, bytes]],
    chunks: list[bytes],
    app_reads_body: bool = True,
) -> tuple[list[dict], bool]:
    queue = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]
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
        "method": "POST",
        "scheme": "http",
        "path": "/api/run",
        "raw_path": b"/api/run",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    asyncio.run(SizeLimitMiddleware(app, max_mb=1)(scope, receive, send))
    return sent, called


def _status(sent: list[dict]) -> int:
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def test_duplicate_identical_content_lengths_fail_closed() -> None:
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


@pytest.mark.parametrize("bad", [b"+1", b"1.0", b"0x10"])
def test_non_decimal_content_length_forms_are_rejected(bad: bytes) -> None:
    sent, called = _exercise(headers=[(b"content-length", bad)], chunks=[b"x"])

    assert _status(sent) == 400
    assert not called


def test_optional_whitespace_around_content_length_is_normalized() -> None:
    sent, called = _exercise(headers=[(b"content-length", b" 1 ")], chunks=[b"x"])

    assert _status(sent) == 204
    assert called


def test_oversized_stream_is_rejected_before_app_even_if_handler_would_not_read_body() -> None:
    sent, called = _exercise(
        headers=[],
        chunks=[b"a" * 700_000, b"b" * 400_000],
        app_reads_body=False,
    )

    assert _status(sent) == 413
    assert not called
