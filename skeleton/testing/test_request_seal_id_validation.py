"""Security regressions for Gate request-correlation IDs."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import Response

from skeleton.api.middleware import GatePolicy, RequestSealMiddleware, get_request_id


def _exercise(request_ids: list[str]) -> tuple[str, str]:
    observed_state: dict[str, str] = {}
    sent: list[dict] = []
    queue = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, receive, send) -> None:
        request = Request(scope, receive=receive)
        observed_state["seal"] = request.state.seal
        response = Response(status_code=204)
        await response(scope, receive, send)

    headers = [(b"x-request-id", value.encode("ascii")) for value in request_ids]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    stack = RequestSealMiddleware(
        app,
        policy=GatePolicy(open_prefixes=("/health",), domains=()),
    )
    asyncio.run(stack(scope, receive, send))

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    response_ids = [
        value.decode("ascii")
        for key, value in response_start["headers"]
        if key.lower() == b"x-request-id"
    ]
    assert len(response_ids) == 1
    return observed_state["seal"], response_ids[0]


def test_valid_single_request_id_is_preserved_end_to_end() -> None:
    state_id, response_id = _exercise(["req.valid-123:abc"])

    assert state_id == "req.valid-123:abc"
    assert response_id == state_id


def test_duplicate_request_ids_are_replaced_before_state_and_response() -> None:
    state_id, response_id = _exercise(["first", "second"])

    assert state_id not in {"first", "second"}
    assert len(state_id) == 16
    assert response_id == state_id


def test_malformed_request_id_is_replaced_before_state_and_response() -> None:
    malformed = "contains space"
    state_id, response_id = _exercise([malformed])

    assert state_id != malformed
    assert len(state_id) == 16
    assert response_id == state_id


def test_get_request_id_rejects_oversized_or_noncanonical_input() -> None:
    assert get_request_id("a" * 129) != "a" * 129
    assert get_request_id(" padded ") != " padded "
    assert get_request_id("ok-id") == "ok-id"