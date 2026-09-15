"""Regression coverage for request ID validation and propagation."""

import asyncio
import json

from starlette.requests import Request
from starlette.responses import Response

from api_middleware import RateLimiterMiddleware, RequestIdMiddleware


def _request(request_ids: str | list[str] | None) -> Request:
    if request_ids is None:
        headers = []
    else:
        values = [request_ids] if isinstance(request_ids, str) else request_ids
        headers = [(b"x-request-id", value.encode("latin-1")) for value in values]
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


def _run(request_ids: str | list[str] | None) -> tuple[str, str, str]:
    request = _request(request_ids)

    async def exercise() -> tuple[str, str, str]:
        response = await RequestIdMiddleware(object()).dispatch(request, _handler)
        return (
            request.state.request_id,
            response.headers["x-request-id"],
            response.headers["x-test-request-id"],
        )

    return asyncio.run(exercise())


def _run_rate_limited(request_ids: str | list[str] | None) -> tuple[str, str, str]:
    request = _request(request_ids)
    limiter = RateLimiterMiddleware(
        object(),
        per_minute=1,
        burst=1,
        max_buckets=8,
        bucket_ttl=300,
    )
    bucket, retry = limiter._bucket_for("192.0.2.10")
    assert bucket is not None
    assert retry == 0.0
    consumed, _ = bucket.take()
    assert consumed

    async def should_not_run(_request: Request) -> Response:
        raise AssertionError("rate-limited request reached the downstream app")

    response = asyncio.run(limiter.dispatch(request, should_not_run))
    payload = json.loads(response.body)
    assert response.status_code == 429
    return (
        request.state.request_id,
        response.headers["x-request-id"],
        payload["request_id"],
    )


def _assert_generated(request_ids: str | list[str] | None) -> str:
    state_id, response_id, handler_id = _run(request_ids)
    assert response_id == state_id == handler_id
    assert len(state_id) == 32
    assert state_id.isascii()
    assert state_id.isalnum()
    int(state_id, 16)
    return state_id


def _assert_generated_triplet(values: tuple[str, str, str]) -> str:
    state_id, response_id, body_id = values
    assert response_id == state_id == body_id
    assert len(state_id) == 32
    int(state_id, 16)
    return state_id


def test_safe_request_id_round_trips_unchanged() -> None:
    state_id, response_id, handler_id = _run("trace_2026-09-15:abc")
    assert state_id == "trace_2026-09-15:abc"
    assert response_id == state_id
    assert handler_id == state_id


def test_invalid_request_id_is_replaced_consistently() -> None:
    generated = _assert_generated("bad id")
    assert generated != "bad id"


def test_control_character_request_id_is_replaced() -> None:
    generated = _assert_generated("bad\nvalue")
    assert "\n" not in generated


def test_oversized_request_id_is_replaced() -> None:
    _assert_generated("a" * 129)


def test_missing_request_id_is_generated_and_propagated() -> None:
    _assert_generated(None)


def test_non_ascii_request_id_is_replaced() -> None:
    _assert_generated("caf\xe9")


def test_duplicate_request_id_headers_are_replaced() -> None:
    generated = _assert_generated(["trace-one", "trace-two"])
    assert generated not in {"trace-one", "trace-two"}


def test_identical_duplicate_request_id_headers_are_still_ambiguous() -> None:
    generated = _assert_generated(["trace-same", "trace-same"])
    assert generated != "trace-same"


def test_generated_ids_do_not_repeat_across_small_adversarial_sample() -> None:
    generated = {_assert_generated(None) for _ in range(128)}
    assert len(generated) == 128


def test_rate_limit_short_circuit_preserves_safe_request_id() -> None:
    state_id, response_id, body_id = _run_rate_limited("trace-rate-limit:1")
    assert state_id == "trace-rate-limit:1"
    assert response_id == state_id == body_id


def test_rate_limit_short_circuit_rejects_duplicate_request_ids() -> None:
    generated = _assert_generated_triplet(_run_rate_limited(["first", "second"]))
    assert generated not in {"first", "second"}


def test_rate_limit_short_circuit_generates_id_when_missing() -> None:
    _assert_generated_triplet(_run_rate_limited(None))
