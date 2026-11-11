"""Network-free adversarial tests for bounded public API and MCP room fanout."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from gameforge.rooms import room_api_gateway as gateway


class FakeResponse:
    is_success = True
    status_code = 200

    def __init__(self, chunks, headers=None):
        self.chunks = chunks
        self.headers = headers or {}

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk


def test_api_request_headers_reject_credentials_and_overlength_values():
    for header in ("Authorization", "Cookie", "X-API-Key", "Forwarded", "Host"):
        with pytest.raises(ValueError):
            gateway._safe_headers({header: "Bearer sensitive"})
    for payload in ({"X-Trace": "x" * 2049}, {"Invalid Name": "ok"}, {"x": "ok\\r\\nInjected: 1"}):
        with pytest.raises(ValueError):
            gateway._safe_headers(payload)
    assert gateway._safe_headers({"X-Trace": "safe"}) == {"X-Trace": "safe"}


def test_http_query_values_and_json_body_are_bounded():
    assert gateway._safe_params({"page": 1}) == {"page": "1"}
    with pytest.raises(ValueError):
        gateway._safe_params({"x": "q" * 513})
    with pytest.raises(ValueError):
        gateway._safe_params({"x": float("inf")})
    with pytest.raises(ValueError):
        gateway._safe_params({"x": ["not scalar"]})
    with pytest.raises(ValueError):
        gateway._safe_payload({"secret": "x" * (129 * 1024)})
    with pytest.raises(ValueError):
        gateway._safe_payload({"numeric": float("nan")})
    assert gateway._safe_payload({"k": True}) == {"k": True}


def test_external_response_is_streamed_under_strict_byte_budget(monkeypatch):
    monkeypatch.setattr(gateway, "_MAX_EXTERNAL_RESPONSE_BYTES", 8)

    async def fetch(response):
        return await gateway._read_external_response(response)

    assert asyncio.run(fetch(FakeResponse([b"ab", b"cde"]))) == "abcde"
    with pytest.raises(ValueError):
        asyncio.run(fetch(FakeResponse([b"abcd", b"efghi"])))
    with pytest.raises(ValueError):
        asyncio.run(fetch(FakeResponse([b"x"], {"content-length": "100"})))
    with pytest.raises(ValueError):
        asyncio.run(fetch(FakeResponse([b"x"], {"content-length": "bogus"})))


@pytest.mark.parametrize("targets,queries", [(17, 0), (0, 33), (17, 33)])
def test_fanout_over_admission_budget_is_rejected_without_execution(targets, queries):
    with pytest.raises(ValueError, match="fanout"):
        asyncio.run(gateway.query_concurrent(
            "room",
            mcp_queries=["safe"] * queries,
            api_targets=[{"url": "https://api.example.test"}] * targets,
        ))


def test_per_room_parallelism_is_bounded(monkeypatch):
    in_flight = 0
    peak = 0
    total = 0

    async def fake_api(_target):
        nonlocal in_flight, peak, total
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.001)
        in_flight -= 1
        total += 1
        return {"channel": "api", "ok": True}

    monkeypatch.setattr(gateway, "_api_query", fake_api)
    result = asyncio.run(gateway.query_concurrent(
        "room-1", api_targets=[{"url": "test"} for _ in range(16)]
    ))
    assert result["counts"] == {"mcp": 0, "api": 16}
    assert total == 16
    assert 1 <= peak <= gateway._MAX_PARALLEL_QUERIES


def test_invalid_mcp_queries_and_sources_rejected():
    for kwargs in (
        {"mcp_queries": ["x" * 4097]},
        {"mcp_queries": [123]},
        {"sources": [None]},
        {"sources": ["x" * 129]},
        {"api_targets": [None]},
    ):
        with pytest.raises(ValueError):
            asyncio.run(gateway.query_concurrent("room", **kwargs))


@pytest.mark.asyncio
async def test_pinned_egress_uses_streaming_body_without_extra_dns_leak(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.test"}))
    resolves = []
    calls = []

    def approved_dns(host):
        resolves.append(host)
        return "93.184.216.34"

    monkeypatch.setattr(gateway, "_resolve_public_host", approved_dns)

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def stream(self, method, path, **kwargs):
            calls.append(("stream", method, path, kwargs))
            yield FakeResponse([b"trusted"], {"content-length": "7"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    response = await gateway._api_query({
        "url": "https://api.example.test/knowledge?q=ok",
        "headers": {"X-Trace": "request"},
    })
    assert response["ok"] is True
    assert response["body"] == "trusted"
    assert resolves == ["api.example.test", "api.example.test"]
    assert calls[0][1]["base_url"] == "https://93.184.216.34"
    assert calls[0][1]["follow_redirects"] is False
    assert calls[0][1]["trust_env"] is False
    assert calls[1][2] == "/knowledge?q=ok"
    assert calls[1][3]["headers"]["Host"] == "api.example.test"
    assert calls[1][3]["extensions"] == {"sni_hostname": "api.example.test"}


@pytest.mark.asyncio
async def test_oversize_upstream_response_never_reaches_caller(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.test"}))
    monkeypatch.setattr(gateway, "_MAX_EXTERNAL_RESPONSE_BYTES", 8)
    monkeypatch.setattr(gateway, "_resolve_public_host", lambda _: "93.184.216.34")

    class FakeClient:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def stream(self, *_args, **_kwargs):
            yield FakeResponse([b"long confidential response"])

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await gateway._api_query({"url": "https://api.example.test/"})
    assert result["ok"] is False
    assert result["error"] == "api_query_failed"
    assert "body" not in result
