from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Iterable

import pytest
from starlette.requests import Request
from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware.security import (  # noqa: E402
    RateLimitMiddleware,
    SizeLimitMiddleware,
    _matches_path_prefix,
    _request_client_ip,
)


def _request(path: str, *, client_ip: str = "10.0.0.1", headers=None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers or [],
            "client": (client_ip, 12345),
            "server": ("testserver", 80),
        }
    )


def test_path_prefix_requires_route_segment_boundary() -> None:
    assert _matches_path_prefix("/api/health", "/api/health")
    assert _matches_path_prefix("/api/health/live", "/api/health")
    assert not _matches_path_prefix("/api/health-check", "/api/health")
    assert not _matches_path_prefix("/api/telemetry/eventual", "/api/telemetry/event")
    assert not _matches_path_prefix("/apiary", "/api")


def test_forwarded_ip_is_untrusted_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEDOCK_TRUSTED_PROXY_CIDRS", raising=False)
    request = _request(
        "/api/run",
        client_ip="10.0.0.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99, 10.0.0.7")],
    )

    assert _request_client_ip(request) == "10.0.0.7"


def test_forwarded_ip_requires_explicit_proxy_peer_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        "/api/run",
        client_ip="10.0.0.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99, 10.0.0.8")],
    )

    assert _request_client_ip(request) == "203.0.113.99"


def test_rate_limit_whitelist_does_not_exempt_lookalikes() -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        RateLimitMiddleware._buckets.clear()
        RateLimitMiddleware._lock = asyncio.Lock()
        middleware = RateLimitMiddleware(app, rps=0.000001, burst=1, max_buckets=8)

        exact = _request("/api/health")
        assert (await middleware.dispatch(exact, call_next)).status_code == 204
        assert (await middleware.dispatch(exact, call_next)).status_code == 204
        assert not RateLimitMiddleware._buckets

        lookalike = _request("/api/health-check")
        assert (await middleware.dispatch(lookalike, call_next)).status_code == 204
        assert (await middleware.dispatch(lookalike, call_next)).status_code == 429

    asyncio.run(scenario())


def test_rate_limit_bucket_cardinality_is_bounded() -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        RateLimitMiddleware._buckets.clear()
        RateLimitMiddleware._lock = asyncio.Lock()
        middleware = RateLimitMiddleware(app, rps=1, burst=2, max_buckets=2)

        for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
            response = await middleware.dispatch(_request("/api/run", client_ip=ip), call_next)
            assert response.status_code == 204

        assert len(RateLimitMiddleware._buckets) == 2
        assert all(key[0] != "10.0.0.1" for key in RateLimitMiddleware._buckets)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rps": 0}, "rps"),
        ({"burst": 0}, "burst"),
        ({"max_buckets": 0}, "bucket cap"),
    ],
)
def test_rate_limit_invalid_configuration_fails_closed(kwargs: dict, message: str) -> None:
    async def app(_scope, _receive, _send) -> None:
        return None

    with pytest.raises(ValueError, match=message):
        RateLimitMiddleware(app, **kwargs)


def _exercise_size_limit(
    chunks: Iterable[bytes],
    *,
    content_lengths: Iterable[str] = (),
) -> tuple[list[dict], list[bytes]]:
    materialized = list(chunks)
    requests = [
        {
            "type": "http.request",
            "body": body,
            "more_body": index < len(materialized) - 1,
        }
        for index, body in enumerate(materialized)
    ]
    if not requests:
        requests.append({"type": "http.request", "body": b"", "more_body": False})

    sent: list[dict] = []
    consumed: list[bytes] = []

    async def receive() -> dict:
        return requests.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(_scope, bounded_receive, bounded_send) -> None:
        body = bytearray()
        while True:
            message = await bounded_receive()
            body.extend(message.get("body") or b"")
            if not message.get("more_body", False):
                break
        consumed.append(bytes(body))
        await bounded_send({"type": "http.response.start", "status": 204, "headers": []})
        await bounded_send({"type": "http.response.body", "body": b""})

    headers = [(b"content-length", value.encode("ascii")) for value in content_lengths]
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
    return sent, consumed


def _status(sent: list[dict]) -> int:
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


def test_streamed_body_without_content_length_cannot_bypass_limit() -> None:
    sent, consumed = _exercise_size_limit([b"a" * 600_000, b"b" * 600_000])

    assert _status(sent) == 413
    assert consumed == []


def test_forged_small_content_length_cannot_bypass_actual_limit() -> None:
    sent, consumed = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        content_lengths=["1"],
    )

    assert _status(sent) == 413
    assert consumed == []


def test_declared_oversize_is_rejected_before_body_read() -> None:
    sent, consumed = _exercise_size_limit([b"x"], content_lengths=[str(2 * 1024 * 1024)])

    assert _status(sent) == 413
    assert consumed == []


@pytest.mark.parametrize("bad", ["not-a-number", "-1"])
def test_malformed_content_length_is_rejected(bad: str) -> None:
    sent, consumed = _exercise_size_limit([b"x"], content_lengths=[bad])

    assert _status(sent) == 400
    assert consumed == []


def test_conflicting_content_lengths_are_rejected() -> None:
    sent, consumed = _exercise_size_limit([b"x"], content_lengths=["1", "2"])

    assert _status(sent) == 400
    assert consumed == []


def test_body_at_limit_passes() -> None:
    sent, consumed = _exercise_size_limit([b"a" * (1024 * 1024)])

    assert _status(sent) == 204
    assert len(consumed) == 1
    assert len(consumed[0]) == 1024 * 1024


def test_non_positive_body_limit_fails_closed() -> None:
    async def app(_scope, _receive, _send) -> None:
        return None

    with pytest.raises(ValueError, match="positive"):
        SizeLimitMiddleware(app, max_mb=0)
