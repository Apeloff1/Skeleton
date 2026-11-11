"""Adversarial bounded egress and resource-admission tests for room API fan-out.

No real network connections: fake DNS and fake HTTPX streaming contexts prove
the checked authority and resource caps without contacting any external host.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import socket

import httpx
import pytest

from gameforge.rooms import room_api_gateway as gateway


class FakeResponse:
    headers = {}
    status_code = 200
    is_success = True

    def __init__(self, chunks, headers=None):
        self.chunks = chunks
        self.headers = headers or {}

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk


def _record(ip="93.184.216.34"):
    return (
        socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
        "", (ip, 443),
    )


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse([b"x"], {"content-length": "oops"}),
        FakeResponse([b"x"], {"content-length": "-1"}),
        FakeResponse([b"x"], {"content-length": str(64 * 1024 + 1)}),
        FakeResponse([b"x" * (64 * 1024), b"y"]),
        FakeResponse([b"x" * (64 * 1024 + 1024)]),
    ],
)
def test_bounded_external_response_denies_oversized_or_malformed_stream(response):
    with pytest.raises(ValueError):
        asyncio.run(gateway._bounded_external_body(response))


def test_bounded_response_accepts_fragmented_utf8_and_crops_public_output():
    result = asyncio.run(gateway._bounded_external_body(FakeResponse([
        b"hello", b" world", b"x" * 4000,
    ])))
    assert result.startswith("hello world")
    assert len(result) == 2000
    assert asyncio.run(gateway._bounded_external_body(FakeResponse([
        b"ok",
    ], {"content-length": "2"}))) == "ok"


@pytest.mark.parametrize("header", [
    "Authorization", "Cookie", "Set-Cookie", "X-API-Key", "X-Auth-Token",
    "Proxy-Authorization", "Proxy-Connection", "Forwarded", "X-Forwarded-For",
    "X-Forwarded-Host", "X-Real-IP", "Host", "Connection", "Upgrade",
])
def test_external_headers_cannot_forward_private_identity(header):
    with pytest.raises(ValueError, match="forbidden"):
        gateway._safe_headers({header: "do-not-forward"})


@pytest.mark.parametrize("headers", [
    {"X-Test": "hello\nHost: evil.invalid"},
    {"X Test": "value"},
    {"X_Test": "value"},
    {"X-Test": "X" * 1025},
    {"X-Test": "café"},
    {f"X-Key-{i}": "v" for i in range(25)},
])
def test_external_header_budget_and_syntax_are_restricted(headers):
    with pytest.raises(ValueError):
        gateway._safe_headers(headers)


def test_request_json_and_query_boundaries_enforce_resource_limits():
    assert gateway._bounded_request_data({"q": "ok"}, kind="params") == {"q": "ok"}
    assert gateway._bounded_request_data({"nested": {"ok": True}}, kind="json")
    for value, kind in [
        ({"long": "x" * 1025}, "params"),
        ({"name": {"nested": "value"}}, "params"),
        ({"q": float("inf")}, "params"),
        ({f"k{i}": i for i in range(25)}, "params"),
        ({"payload": "x" * (16 * 1024 + 1)}, "json"),
        ({"bad": object()}, "json"),
    ]:
        with pytest.raises(ValueError):
            gateway._bounded_request_data(value, kind=kind)


def test_dns_answer_fanout_is_bounded(monkeypatch):
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **k: [_record()] * 33)
    with pytest.raises(ValueError, match="too many DNS"):
        gateway._resolve_public_host("api.example.com")


@pytest.mark.asyncio
async def test_external_response_limit_fails_closed_without_credential_echo(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.com"}))
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **k: [_record()])

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://93.184.216.34"
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def stream(self, method, path, **kwargs):
            assert method == "GET"
            assert path.startswith("/v1?")
            assert kwargs["extensions"] == {"sni_hostname": "api.example.com"}
            assert kwargs["headers"]["Host"] == "api.example.com"
            yield FakeResponse([b"Z" * (64 * 1024 + 1)])

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await gateway._api_query({
        "name": "Bearer secret",
        "url": "https://api.example.com/v1?q=test",
    })
    assert result == {
        "channel": "api", "target": "external-api",
        "ok": False, "error": "api_query_failed",
    }


@pytest.mark.asyncio
async def test_invalid_target_is_cleanly_denied_without_gather_crash():
    result = await gateway._api_query("https://internal.invalid")
    assert result["ok"] is False
    assert result["error"] == "invalid_api_target"


def test_excessive_per_request_fanout_fails_before_allocation():
    for args in [
        {"mcp_queries": ["q"] * 33},
        {"api_targets": [{}] * 33},
        {"mcp_queries": ["q"] * 32, "api_targets": [{}] * 17},
        {"mcp_queries": ["q" * 2049]},
        {"api_targets": ["untrusted"]},
        {"sources": ["one"] * 17},
        {"sources": [None]},
    ]:
        with pytest.raises(ValueError, match="admission bounds"):
            asyncio.run(gateway.query_concurrent("room", **args))


@pytest.mark.asyncio
async def test_room_executes_at_most_eight_concurrent_jobs(monkeypatch):
    active = 0
    peak = 0

    async def fake_work(channel):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.001)
            return {"channel": channel, "ok": True}
        finally:
            active -= 1

    async def fake_mcp(query, sources):
        return await fake_work("mcp")

    async def fake_api(target):
        return await fake_work("api")

    monkeypatch.setattr(gateway, "_mcp_query", fake_mcp)
    monkeypatch.setattr(gateway, "_api_query", fake_api)
    result = await gateway.query_concurrent(
        "room", mcp_queries=["q"] * 32, api_targets=[{}] * 16
    )
    assert result["ok"] is True
    assert result["counts"] == {"mcp": 32, "api": 16}
    assert peak <= 8
    assert active == 0
