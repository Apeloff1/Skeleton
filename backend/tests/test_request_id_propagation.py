"""Regression coverage for request ID validation and propagation."""

import asyncio

from starlette.requests import Request
from starlette.responses import Response

from api_middleware import RequestIdMiddleware


def _request(request_id: str | None) -> Request:
    headers = [] if request_id is None else [(b"x-request-id", request_id.encode())]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": headers,
            "client": ("192.0.2.10", 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def _handler(request: Request) -> Response:
    response = Response(status_code=200)
    response.headers["X-Test-Request-Id"] = request.state.request_id
    return response


def _run(request_id: str | None) -> tuple[str, str, str]:
    request = _request(request_id)

    async def exercise() -> tuple[str, str, str]:
        response = await RequestIdMiddleware(object()).dispatch(request, _handler)
        return (
            request.state.request_id,
            response.headers["x-request-id"],
            response.headers["x-test-request-id"],
        )

    return asyncio.run(exercise())


def test_safe_request_id_round_trips_unchanged() -> None:
    state_id, response_id, handler_id = _run("trace_2026-09-15:abc")
    assert state_id == "trace_2026-09-15:abc"
    assert response_id == state_id
    assert handler_id == state_id


def test_invalid_request_id_is_replaced_consistently() -> None:
    state_id, response_id, handler_id = _run("bad id")
    assert state_id != "bad id"
    assert response_id == state_id
    assert handler_id == state_id
    assert len(state_id) == 16


def test_control_character_request_id_is_replaced() -> None:
    state_id, response_id, handler_id = _run("bad\nvalue")
    assert response_id == state_id == handler_id
    assert "\n" not in state_id


def test_oversized_request_id_is_replaced() -> None:
    state_id, response_id, handler_id = _run("a" * 129)
    assert response_id == state_id == handler_id
    assert len(state_id) == 16


def test_missing_request_id_is_generated_and_propagated() -> None:
    state_id, response_id, handler_id = _run(None)
    assert response_id == state_id == handler_id
    assert len(state_id) == 16
