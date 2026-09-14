from __future__ import annotations

import asyncio

from starlette.requests import Request

from api_middleware import _request_id, _safe_log_field
from core.client_ip import resolve_client_ip
from middleware.security import RateLimitMiddleware, SizeLimitMiddleware


def _request(peer: str, headers: dict[str, str] | None = None) -> Request:
    encoded = [
        (key.lower().encode("ascii"), value.encode("ascii"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": encoded,
            "client": (peer, 43210),
            "server": ("testserver", 80),
        }
    )


def test_untrusted_peer_cannot_spoof_x_forwarded_for(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.0/8")
    request = _request("198.51.100.10", {"x-forwarded-for": "203.0.113.99"})
    assert resolve_client_ip(request) == "198.51.100.10"


def test_trusted_proxy_can_forward_client_address(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request("10.0.0.2", {"x-forwarded-for": "203.0.113.25"})
    assert resolve_client_ip(request) == "203.0.113.25"


def test_forwarded_chain_stops_at_first_untrusted_hop(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request(
        "10.0.0.3",
        {"x-forwarded-for": "192.0.2.99, 198.51.100.7, 10.0.0.2"},
    )
    assert resolve_client_ip(request) == "198.51.100.7"


def test_malformed_forwarded_chain_fails_closed_to_peer(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    request = _request("10.0.0.3", {"x-forwarded-for": "203.0.113.1, not-an-ip"})
    assert resolve_client_ip(request) == "10.0.0.3"


def test_request_id_rejects_control_characters():
    request = _request("127.0.0.1", {"x-request-id": "ok\r\ninjected=true"})
    request_id = _request_id(request)
    assert request_id != "ok\r\ninjected=true"
    assert "\r" not in request_id
    assert "\n" not in request_id
    assert len(request_id) == 16


def test_request_id_preserves_safe_value():
    request = _request("127.0.0.1", {"x-request-id": "req-1234.safe:value"})
    assert _request_id(request) == "req-1234.safe:value"


def test_log_fields_are_single_line_and_bounded():
    sanitized = _safe_log_field("/api/demo\r\nforged=true\x00tail", limit=24)
    assert "\r" not in sanitized
    assert "\n" not in sanitized
    assert "\x00" not in sanitized
    assert len(sanitized) <= 24


def test_invalid_rate_limit_float_falls_back_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_RPS", "not-a-float")

    async def app(scope, receive, send):
        return None

    middleware = RateLimitMiddleware(app)
    assert middleware._rps == 2.0


def test_nonfinite_rate_limit_float_falls_back(monkeypatch):
    monkeypatch.setenv("CODEDOCK_RATE_LIMIT_RPS", "nan")

    async def app(scope, receive, send):
        return None

    middleware = RateLimitMiddleware(app)
    assert middleware._rps == 2.0


def test_invalid_programmatic_burst_falls_back():
    async def app(scope, receive, send):
        return None

    middleware = RateLimitMiddleware(app, burst="not-an-int")
    assert middleware._burst >= 1


async def _body_echo_app(scope, receive, send):
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _run_size_limit(*, headers: list[tuple[bytes, bytes]], chunks: list[bytes], max_mb: int = 1):
    middleware = SizeLimitMiddleware(_body_echo_app, max_mb=max_mb)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/upload",
        "raw_path": b"/api/upload",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    events = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    if not events:
        events = [{"type": "http.request", "body": b"", "more_body": False}]
    sent: list[dict] = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def _status(events: list[dict]) -> int:
    return next(event["status"] for event in events if event["type"] == "http.response.start")


def test_size_limit_rejects_declared_oversize_before_reading_body():
    events = _run_size_limit(
        headers=[(b"content-length", str(2 * 1024 * 1024).encode("ascii"))],
        chunks=[b"small"],
    )
    assert _status(events) == 413


def test_size_limit_rejects_chunked_body_without_content_length():
    events = _run_size_limit(
        headers=[(b"transfer-encoding", b"chunked")],
        chunks=[b"a" * 700_000, b"b" * 700_000],
    )
    assert _status(events) == 413


def test_size_limit_rejects_duplicate_content_length():
    events = _run_size_limit(
        headers=[(b"content-length", b"5"), (b"content-length", b"5")],
        chunks=[b"hello"],
    )
    assert _status(events) == 400


def test_size_limit_rejects_content_length_with_transfer_encoding():
    events = _run_size_limit(
        headers=[(b"content-length", b"5"), (b"transfer-encoding", b"chunked")],
        chunks=[b"hello"],
    )
    assert _status(events) == 400


def test_size_limit_rejects_invalid_content_length():
    events = _run_size_limit(headers=[(b"content-length", b"not-a-number")], chunks=[b"hello"])
    assert _status(events) == 400


def test_size_limit_rejects_non_ascii_content_length():
    events = _run_size_limit(headers=[(b"content-length", b"\xff")], chunks=[b"hello"])
    assert _status(events) == 400


def test_size_limit_rejects_negative_content_length():
    events = _run_size_limit(headers=[(b"content-length", b"-1")], chunks=[b"hello"])
    assert _status(events) == 400


def test_size_limit_clamps_invalid_programmatic_limit():
    middleware = SizeLimitMiddleware(_body_echo_app, max_mb=-100)
    assert middleware.max_bytes == 1024 * 1024


def test_size_limit_allows_body_under_cap():
    events = _run_size_limit(headers=[], chunks=[b"a" * 512_000])
    assert _status(events) == 200
