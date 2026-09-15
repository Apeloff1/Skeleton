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

import middleware.security as security  # noqa: E402
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


def _reset_rate_limit() -> None:
    RateLimitMiddleware._buckets.clear()
    RateLimitMiddleware._lock = asyncio.Lock()
    RateLimitMiddleware._capacity_rejections = 0
    RateLimitMiddleware._expired_prunes = 0


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


def test_forwarded_ip_requires_trusted_immediate_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        "/api/run",
        client_ip="192.0.2.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    assert _request_client_ip(request) == "192.0.2.7"


def test_forwarded_ip_walks_trusted_chain_right_to_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        "/api/run",
        client_ip="10.0.0.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99, 10.0.0.8")],
    )
    assert _request_client_ip(request) == "203.0.113.99"


@pytest.mark.parametrize(
    "headers",
    [
        [
            (b"x-forwarded-for", b"203.0.113.1"),
            (b"x-forwarded-for", b"203.0.113.2"),
        ],
        [(b"x-forwarded-for", b"not-an-ip")],
        [(b"x-forwarded-for", b"203.0.113.1,,10.0.0.8")],
    ],
)
def test_ambiguous_or_malformed_forwarding_chain_fails_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
    headers,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request("/api/run", client_ip="10.0.0.7", headers=headers)
    assert _request_client_ip(request) == "10.0.0.7"


def test_malformed_proxy_cidr_configuration_disables_proxy_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,not-a-cidr")
    request = _request(
        "/api/run",
        client_ip="10.0.0.7",
        headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    assert _request_client_ip(request) == "10.0.0.7"


def test_rate_limit_whitelist_does_not_exempt_lookalikes_or_leaf_children() -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        _reset_rate_limit()
        middleware = RateLimitMiddleware(app, rps=0.000001, burst=1, max_buckets=8)

        exact = _request("/api/health")
        assert (await middleware.dispatch(exact, call_next)).status_code == 204
        assert (await middleware.dispatch(exact, call_next)).status_code == 204
        assert not RateLimitMiddleware._buckets

        health_child = _request("/api/health/live")
        assert (await middleware.dispatch(health_child, call_next)).status_code == 204
        assert (await middleware.dispatch(health_child, call_next)).status_code == 204
        assert not RateLimitMiddleware._buckets

        lookalike = _request("/api/health-check")
        assert (await middleware.dispatch(lookalike, call_next)).status_code == 204
        assert (await middleware.dispatch(lookalike, call_next)).status_code == 429

        _reset_rate_limit()
        leaf_child = _request("/api/telemetry/event/child")
        assert (await middleware.dispatch(leaf_child, call_next)).status_code == 204
        assert (await middleware.dispatch(leaf_child, call_next)).status_code == 429

    asyncio.run(scenario())


def test_rate_limit_bucket_cardinality_is_bounded_without_fresh_burst_on_churn() -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        _reset_rate_limit()
        middleware = RateLimitMiddleware(app, rps=0.000001, burst=1, max_buckets=2)

        first = _request("/api/run", client_ip="10.0.0.1")
        second = _request("/api/run", client_ip="10.0.0.2")
        attacker = _request("/api/run", client_ip="10.0.0.3")

        assert (await middleware.dispatch(first, call_next)).status_code == 204
        assert (await middleware.dispatch(second, call_next)).status_code == 204

        # A new identity cannot evict an exhausted bucket and obtain a fresh burst.
        assert (await middleware.dispatch(attacker, call_next)).status_code == 429
        assert len(RateLimitMiddleware._buckets) == 2
        assert ("10.0.0.1", "/api/run") in RateLimitMiddleware._buckets
        assert ("10.0.0.2", "/api/run") in RateLimitMiddleware._buckets
        assert (await middleware.dispatch(first, call_next)).status_code == 429

    asyncio.run(scenario())


def test_rate_limit_expired_state_is_pruned_before_capacity_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        _reset_rate_limit()
        ticks = iter([100.0, 100.0, 102.0])
        monkeypatch.setattr(security, "_monotonic", lambda: next(ticks))
        middleware = RateLimitMiddleware(
            app, rps=1, burst=2, max_buckets=2, bucket_ttl=1
        )

        for ip in ("10.0.0.1", "10.0.0.2"):
            assert (
                await middleware.dispatch(_request("/api/run", client_ip=ip), call_next)
            ).status_code == 204

        replacement = await middleware.dispatch(
            _request("/api/run", client_ip="10.0.0.3"), call_next
        )
        assert replacement.status_code == 204
        assert len(RateLimitMiddleware._buckets) == 1
        assert list(RateLimitMiddleware._buckets)[0][0] == "10.0.0.3"
        assert RateLimitMiddleware._expired_prunes == 2

    asyncio.run(scenario())


def test_rate_limit_config_shrink_preserves_hard_bucket_cap() -> None:
    async def app(_scope, _receive, _send) -> None:
        return None

    _reset_rate_limit()
    RateLimitMiddleware._buckets[("1", "/api/a")] = security._Bucket(0.0, 1.0)
    RateLimitMiddleware._buckets[("2", "/api/a")] = security._Bucket(0.0, 1.0)
    RateLimitMiddleware._buckets[("3", "/api/a")] = security._Bucket(0.0, 1.0)
    RateLimitMiddleware(app, rps=1, burst=1, max_buckets=2, bucket_ttl=300)
    assert len(RateLimitMiddleware._buckets) == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rps": 0}, "rps"),
        ({"rps": float("nan")}, "rps"),
        ({"rps": float("inf")}, "rps"),
        ({"burst": 0}, "burst"),
        ({"max_buckets": 0}, "bucket cap"),
        ({"bucket_ttl": 0}, "bucket ttl"),
        ({"bucket_ttl": float("inf")}, "bucket ttl"),
    ],
)
def test_rate_limit_invalid_configuration_fails_closed(kwargs: dict, message: str) -> None:
    async def app(_scope, _receive, _send) -> None:
        return None

    with pytest.raises(ValueError, match=message):
        RateLimitMiddleware(app, **kwargs)


def test_monotonic_refill_state_never_moves_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        _reset_rate_limit()
        ticks = iter([100.0, 99.0, 100.0])
        monkeypatch.setattr(security, "_monotonic", lambda: next(ticks))
        middleware = RateLimitMiddleware(app, rps=1, burst=1, max_buckets=2)
        request = _request("/api/run")

        assert (await middleware.dispatch(request, call_next)).status_code == 204
        assert (await middleware.dispatch(request, call_next)).status_code == 429
        assert (await middleware.dispatch(request, call_next)).status_code == 429

    asyncio.run(scenario())


def _exercise_size_limit(
    chunks: Iterable[bytes],
    *,
    content_lengths: Iterable[str] = (),
    method: str = "POST",
    path: str = "/api/run",
    extra_headers: Iterable[tuple[bytes, bytes]] = (),
    read_mode: str = "all",
) -> tuple[list[dict], list[bytes], list[bool]]:
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
    called: list[bool] = []

    async def receive() -> dict:
        if requests:
            return requests.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(_scope, bounded_receive, bounded_send) -> None:
        called.append(True)
        body = bytearray()
        if read_mode == "all":
            while True:
                message = await bounded_receive()
                if message.get("type") != "http.request":
                    break
                body.extend(message.get("body") or b"")
                if not message.get("more_body", False):
                    break
        elif read_mode == "first":
            message = await bounded_receive()
            body.extend(message.get("body") or b"")
        elif read_mode != "none":
            raise AssertionError(f"unknown read mode: {read_mode}")

        consumed.append(bytes(body))
        await bounded_send({"type": "http.response.start", "status": 204, "headers": []})
        await bounded_send({"type": "http.response.body", "body": b""})

    headers = [(b"content-length", value.encode("ascii")) for value in content_lengths]
    headers.extend(extra_headers)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    asyncio.run(SizeLimitMiddleware(app, max_mb=1)(scope, receive, send))
    return sent, consumed, called


def _status(sent: list[dict]) -> int:
    return next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )


def test_streamed_body_without_content_length_cannot_bypass_limit() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000]
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


def test_forged_small_content_length_cannot_bypass_actual_limit() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        content_lengths=["1"],
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


def test_oversize_is_rejected_even_if_downstream_would_not_read_body() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        read_mode="none",
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


@pytest.mark.parametrize("method", ["GET", "DELETE", "OPTIONS"])
def test_body_limit_applies_to_every_api_method(method: str) -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        method=method,
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


def test_non_api_body_is_not_intercepted() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        path="/apiary",
    )
    assert _status(sent) == 204
    assert called == [True]
    assert len(consumed[0]) == 1_200_000


def test_declared_oversize_is_rejected_before_body_read() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        content_lengths=[str(2 * 1024 * 1024)],
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


@pytest.mark.parametrize(
    "bad",
    ["not-a-number", "-1", "+1", "1_0", "", "1,1"],
)
def test_malformed_content_length_is_rejected(bad: str) -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        content_lengths=[bad],
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_extremely_large_content_length_is_rejected_without_integer_parse_dos() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        content_lengths=["9" * 5000],
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


@pytest.mark.parametrize("values", [["1", "2"], ["1", "1"]])
def test_duplicate_content_lengths_are_rejected(values: list[str]) -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        content_lengths=values,
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_content_length_and_transfer_encoding_are_rejected_together() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        content_lengths=["1"],
        extra_headers=[(b"transfer-encoding", b"chunked")],
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_unsupported_transfer_encoding_is_rejected() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        extra_headers=[(b"transfer-encoding", b"gzip")],
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_duplicate_transfer_encoding_headers_are_rejected() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"x"],
        extra_headers=[
            (b"transfer-encoding", b"chunked"),
            (b"transfer-encoding", b"chunked"),
        ],
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_chunked_body_is_counted_and_replayed() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 400_000, b"b" * 400_000],
        extra_headers=[(b"transfer-encoding", b"chunked")],
    )
    assert _status(sent) == 204
    assert called == [True]
    assert len(consumed[0]) == 800_000


def test_content_length_must_match_streamed_body() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"abc"],
        content_lengths=["2"],
    )
    assert _status(sent) == 400
    assert consumed == []
    assert called == []


def test_body_at_limit_passes_and_replays_all_chunks() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 524_288, b"b" * 524_288]
    )
    assert _status(sent) == 204
    assert called == [True]
    assert len(consumed) == 1
    assert len(consumed[0]) == 1024 * 1024


def test_prebuffering_protects_partial_reader_from_oversize_tail() -> None:
    sent, consumed, called = _exercise_size_limit(
        [b"a" * 600_000, b"b" * 600_000],
        read_mode="first",
    )
    assert _status(sent) == 413
    assert consumed == []
    assert called == []


def test_non_positive_body_limit_fails_closed() -> None:
    async def app(_scope, _receive, _send) -> None:
        return None

    with pytest.raises(ValueError, match="positive"):
        SizeLimitMiddleware(app, max_mb=0)
