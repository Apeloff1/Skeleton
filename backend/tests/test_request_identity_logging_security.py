from __future__ import annotations

import asyncio
import logging

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import AccessLogMiddleware, RateLimiterMiddleware, RequestIdMiddleware
from middleware.security import AuditMiddleware


def _request(raw_ids: list[bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/request-id-test",
            "raw_path": b"/api/request-id-test",
            "query_string": b"",
            "headers": [(b"x-request-id", value) for value in raw_ids],
            "client": ("198.51.100.40", 12345),
            "server": ("testserver", 80),
        }
    )


async def _endpoint(_request: Request) -> Response:
    return Response(status_code=204)


def _reset_logging_state() -> None:
    api_middleware._lat_lock = None
    api_middleware._lat_ring.clear()
    AuditMiddleware._buf.clear()


@pytest.mark.parametrize(
    "raw_id",
    [
        b"bad\nrequest-id",
        b"bad\rrequest-id",
        b"bad\x00request-id",
        b"x" * 129,
    ],
)
def test_invalid_request_ids_are_replaced_with_header_safe_canonical_ids(raw_id: bytes) -> None:
    async def scenario() -> tuple[Request, Response]:
        request = _request([raw_id])
        middleware = RequestIdMiddleware(object())
        response = await middleware.dispatch(request, _endpoint)
        return request, response

    request, response = asyncio.run(scenario())
    canonical = request.state.request_id

    assert canonical == response.headers["x-request-id"]
    assert api_middleware._REQUEST_ID_RE.fullmatch(canonical)
    assert len(canonical) <= 128
    assert "\n" not in canonical
    assert "\r" not in canonical
    assert "\x00" not in canonical


def test_control_char_request_id_cannot_inject_access_log_line(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_logging_state()
    monkeypatch.setattr(api_middleware, "_ACCESS_LOG", True)
    request = _request([b"bad\nforged-entry=1"])

    async def scenario() -> Response:
        access = AccessLogMiddleware(object())
        request_id = RequestIdMiddleware(object())

        async def through_access(current: Request) -> Response:
            return await access.dispatch(current, _endpoint)

        return await request_id.dispatch(request, through_access)

    with caplog.at_level(logging.INFO, logger="api.middleware"):
        response = asyncio.run(scenario())

    canonical = response.headers["x-request-id"]
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "api.middleware"
    ]

    assert messages
    assert all("\n" not in message and "\r" not in message for message in messages)
    assert all("forged-entry=1" not in message for message in messages)
    assert any(f"rid={canonical}" in message for message in messages)


def test_rate_limit_log_cannot_be_line_injected_by_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = _request([b"attacker\nforged-rate-limit=1"])
    limiter = RateLimiterMiddleware(
        object(), per_minute=1, burst=1, max_buckets=4, bucket_ttl=300
    )
    bucket, _ = limiter._bucket_for("198.51.100.40")
    assert bucket is not None
    consumed, _ = bucket.take()
    assert consumed

    with caplog.at_level(logging.WARNING, logger="api.middleware"):
        response = asyncio.run(limiter.dispatch(request, _endpoint))

    canonical = request.state.request_id
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "api.middleware"
    ]

    assert response.status_code == 429
    assert response.headers["x-request-id"] == canonical
    assert api_middleware._REQUEST_ID_RE.fullmatch(canonical)
    assert messages
    assert all("\n" not in message and "\r" not in message for message in messages)
    assert all("forged-rate-limit=1" not in message for message in messages)
    assert any(f"rid={canonical}" in message for message in messages)


def test_one_canonical_id_reaches_response_log_and_audit(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_logging_state()
    monkeypatch.setattr(api_middleware, "_ACCESS_LOG", True)
    request = _request([b"attacker\nsecond-log-line"])

    async def scenario() -> Response:
        access = AccessLogMiddleware(object())
        audit = AuditMiddleware(object())
        request_id = RequestIdMiddleware(object())

        async def through_access(current: Request) -> Response:
            return await access.dispatch(current, _endpoint)

        async def through_audit(current: Request) -> Response:
            return await audit.dispatch(current, through_access)

        return await request_id.dispatch(request, through_audit)

    with caplog.at_level(logging.INFO, logger="api.middleware"):
        response = asyncio.run(scenario())

    canonical = request.state.request_id
    audit_entry = AuditMiddleware.snapshot(limit=1)["entries"][-1]
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "api.middleware"
    ]

    assert canonical == response.headers["x-request-id"]
    assert audit_entry["rid"] == canonical
    assert any(f"rid={canonical}" in message for message in messages)
    assert all("second-log-line" not in message for message in messages)
