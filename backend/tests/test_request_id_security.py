"""Regression tests for request-ID validation, reflection, and log safety."""
from __future__ import annotations

import asyncio

from api_middleware import RequestIdMiddleware, _request_id, _safe_log_field
from starlette.requests import Request
from starlette.responses import Response


def _request(request_id: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": headers,
            "client": ("198.51.100.9", 43210),
            "server": ("testserver", 80),
        }
    )


def test_oversized_request_id_is_replaced() -> None:
    request = _request("a" * 129)

    generated = _request_id(request)

    assert generated != "a" * 129
    assert len(generated) == 16
    assert generated.isalnum()


def test_control_character_request_id_is_replaced() -> None:
    request = _request("safe\r\nforged-header:value")

    generated = _request_id(request)

    assert "\r" not in generated
    assert "\n" not in generated
    assert generated != "safe\r\nforged-header:value"


def test_safe_request_id_is_preserved_end_to_end() -> None:
    request = _request("req-123.safe:value")

    async def downstream(current: Request) -> Response:
        assert current.state.request_id == "req-123.safe:value"
        return Response(status_code=204)

    middleware = RequestIdMiddleware(lambda scope, receive, send: None)
    response = asyncio.run(middleware.dispatch(request, downstream))

    assert response.headers["X-Request-Id"] == "req-123.safe:value"
    assert request.state.request_id == response.headers["X-Request-Id"]


def test_replacement_request_id_is_propagated_consistently() -> None:
    request = _request("x" * 4096)
    observed: dict[str, str] = {}

    async def downstream(current: Request) -> Response:
        observed["state"] = current.state.request_id
        return Response(status_code=200)

    middleware = RequestIdMiddleware(lambda scope, receive, send: None)
    response = asyncio.run(middleware.dispatch(request, downstream))

    assert observed["state"] == response.headers["X-Request-Id"]
    assert len(observed["state"]) == 16


def test_untrusted_log_metadata_is_single_line_and_bounded() -> None:
    value = "prefix\r\nforged=true\x00" + ("x" * 10_000)

    sanitized = _safe_log_field(value, limit=128)

    assert "\r" not in sanitized
    assert "\n" not in sanitized
    assert "\x00" not in sanitized
    assert len(sanitized) == 128
