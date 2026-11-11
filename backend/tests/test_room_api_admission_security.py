"""Adversarial egress resource budgets for concurrent external room APIs."""
from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager

import httpx
import pytest

from gameforge.rooms import room_api_gateway as gateway


class FakeResponse:
    status_code = 200
    is_success = True

    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}
        self.reads = 0

    async def aiter_bytes(self):
        for chunk in self._chunks:
            self.reads += 1
            yield chunk


@pytest.mark.asyncio
async def test_response_declared_body_oversize_rejected_before_read():
    response = FakeResponse([b"secret"], {"content-length": str(gateway._MAX_RESPONSE_BYTES + 1)})
    with pytest.raises(ValueError, match="byte budget"):
        await gateway._bounded_http_body(response)
    assert response.reads == 0


@pytest.mark.asyncio
async def test_chunked_body_budget_stops_later_chunks():
    chunks = [b"A" * gateway._MAX_RESPONSE_BYTES, b"B", b"should-never-read"]
    response = FakeResponse(chunks)
    with pytest.raises(ValueError, match="byte budget"):
        await gateway._bounded_http_body(response)
    assert response.reads == 2


@pytest.mark.asyncio
async def test_content_length_malformed_fails_closed():
    for value in ("abc", "-1"):
        with pytest.raises(ValueError):
            await gateway._bounded_http_body(FakeResponse([b"short"], {"content-length": value}))


@pytest.mark.asyncio
async def test_bounded_content_is_decoded_and_presented_short():
    response = FakeResponse([b"A" * 2000, b"B" * 10])
    output = await gateway._bounded_http_body(response)
    assert output == "A" * 2000
    assert response.reads == 2


@pytest.mark.parametrize("header", [
    {"Host": "private.internal"},
    {"Content-Length": "42"},
    {"Transfer-Encoding": "chunked"},
    {"Upgrade": "websocket"},
    {"X-Injection": "ok\r\nHost: private.internal"},
    {"X-Too-Big": "x" * 8193},
    {"X Invalid": "value"},
    {"\tX-Weird": "value"},
])
def test_forbidden_or_oversized_headers_rejected(header):
    with pytest.raises(ValueError):
        gateway._safe_headers(header)


@pytest.mark.parametrize("payload", [
    {"blob": "A" * (64 * 1024)},
    {"number": math.inf},
    {"number": math.nan},
    {"list": list(range(1025))},
    {"nested": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": 1}}}}}}}}}},
])
def test_json_payload_rejected_at_allocation_boundary(payload):
    with pytest.raises(ValueError):
        gateway._bounded_json(payload)


def test_bounded_json_and_params_allow_normal_request():
    value = {"message": "hello", "nested": {"count": 3, "ok": True}}
    assert gateway._bounded_json(value) == value
    assert gateway._safe_params({"q": "safe", "page": 2}) == {"q": "safe", "page": "2"}
    with pytest.raises(ValueError):
        gateway._safe_params({"amount": float("inf")})


@pytest.mark.asyncio
async def test_disabled_external_api_does_not_echo_query_credentials(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", False)
    result = await gateway._api_query({"url": "https://safe.example/path?access_token=SECRET_CANARY"})
    assert result["target"] == "external_api"
    assert "SECRET_CANARY" not in str(result)


@pytest.mark.asyncio
async def test_room_fanout_rejects_unbounded_and_invalid_workloads():
    for options in [
        {"mcp_queries": ["x"] * (gateway._MAX_MCP_QUERIES + 1)},
        {"api_targets": [{}] * (gateway._MAX_API_TARGETS + 1)},
        {"sources": ["x"] * (gateway._MAX_SOURCES + 1)},
        {"mcp_queries": [""]},
        {"mcp_queries": ["a" * 4097]},
        {"api_targets": [None]},
        {"sources": [123]},
    ]:
        with pytest.raises(ValueError, match="admission budget"):
            await gateway.query_concurrent("room", **options)


@pytest.mark.asyncio
async def test_room_fanout_never_exceeds_eight_active_operations(monkeypatch):
    active = peak = 0

    async def probe(query, sources):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        active -= 1
        return {"channel": "mcp", "query": query, "ok": True}

    monkeypatch.setattr(gateway, "_mcp_query", probe)
    result = await gateway.query_concurrent(
        "room", mcp_queries=[f"query-{index}" for index in range(32)]
    )
    assert result["counts"] == {"mcp": 32, "api": 0}
    assert 1 <= peak <= gateway._MAX_CONCURRENT_QUERIES


@pytest.mark.asyncio
async def test_external_api_stream_is_bounded_and_pinned(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"safe.example"}))
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *args, **kwargs: [
        (gateway.socket.AF_INET, gateway.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    ])
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        @asynccontextmanager
        async def stream(self, method, target, **kwargs):
            calls.append(("stream", method, target, kwargs))
            yield FakeResponse([b"x" * gateway._MAX_RESPONSE_BYTES, b"overflow"])

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = await gateway._api_query({
        "url": "https://safe.example/data",
        "name": "Test service",
        "params": {"q": "safe"},
    })
    assert result == {
        "channel": "api", "target": "Test service", "ok": False,
        "error": "api_query_failed",
    }
    assert calls[0][1]["base_url"] == "https://93.184.216.34"
    assert calls[0][1]["follow_redirects"] is False
    assert calls[0][1]["trust_env"] is False
    assert calls[1][3]["extensions"] == {"sni_hostname": "safe.example"}
