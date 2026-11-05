"""Source-only canonical engine authority, proxy and transport credential regressions.

These checks are intentionally offline: no HTTP request is permitted to leave a
MockTransport. A bearer token must never be sent to malformed engine URLs, an
ambient corporate proxy, or an HTTP header containing control characters.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from core import engine_client as engine
from core.engine_client import EngineClient, EngineClientConfig, EngineProtocolError


TOKEN = "test-engine-token-" + "f" * 64


@pytest.mark.parametrize("url", [
    "https://trusted.example.com@evil.example",
    "http://service:password@skeleton:8001",
    "http://skeleton:8001/path",
    "https://skeleton:8001/api/v1/engine",
    "https://skeleton:8001/?search=engines",
    "https://skeleton:8001/#fragment",
    "https://skeleton:8001/?",
    "https://skeleton:8001/#",
    "http://skeleton:8001?redirect=https://evil.example",
    "http://skeleton:8001#test",
    "http://skeleton:8001\\@evil.example",
    "http://skeleton:8001\\evil",
    "http://skeleton:8001:8002",
    "http://skeleton:99999",
    "http://skeleton:0",
    "http://skeleton:-1",
    "http://skeleton:8001/../",
    "http://skeleton:8001/%2e%2e",
    "http://%73keleton:8001",
    "http://skeleton..example",
    "http://-skeleton.example",
    "http://skeleton-.example",
    "http://skeleton.example:8080 ",
    "http://skeleton.example\nX-Injected: evil",
    "http://skeleton.example\t:8080",
    "http://[::1",
    "http://[bad-ipv6]:8001",
    "https://skeleton.example:443/credentials",
    "ftp://skeleton:8001",
    "file:///etc/passwd",
    "//skeleton:8001",
    "skeleton:8001",
    "",
])
def test_malformed_engine_authority_rejected_at_construction(url):
    with pytest.raises(EngineProtocolError):
        EngineClientConfig(base_url=url, service_token=TOKEN)


@pytest.mark.parametrize("url,expected", [
    ("http://skeleton:8001", "http://skeleton:8001"),
    ("http://SKELETON:8001/", "http://skeleton:8001"),
    ("https://engine.example.org", "https://engine.example.org"),
    ("https://engine.example.org:8443/", "https://engine.example.org:8443"),
    ("http://127.0.0.1:8020", "http://127.0.0.1:8020"),
    ("http://[::1]:8020", "http://[::1]:8020"),
    ("https://host.docker.internal:8443", "https://host.docker.internal:8443"),
])
def test_expected_docker_loopback_ipv6_and_https_origins_remain_supported(url, expected):
    config = EngineClientConfig(base_url=url, service_token=TOKEN)
    assert config.base_url == expected
    client = EngineClient(config)
    assert client._url("/providers") == expected + "/api/v1/engine/providers"


@pytest.mark.parametrize("token", [
    "x" * 31, "x" * 4097, "x" * 32 + "\r\nx-malicious: yes",
    "\n" + "x" * 32, "x" * 32 + " ", "not ascii: 𐀀" + "x" * 32,
    "x" * 31 + "\t", "x" * 31 + "\0",
])
def test_service_token_rejected_before_it_reaches_http_headers(token):
    with pytest.raises(EngineProtocolError):
        EngineClientConfig(base_url="http://skeleton:8001", service_token=token)


@pytest.mark.parametrize("principal", [
    "bad\nheader: injected", "bad\rheader: injected", " ", "\t",
    "scope name", "snowman☃", "x" * 513,
])
def test_service_principal_is_safe_for_header_authority(principal):
    with pytest.raises(EngineProtocolError):
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal=principal,
            service_token=TOKEN,
        )


@pytest.mark.parametrize("trace", [
    "\nnew: header", "trace\rid", "trace id", "\x00trace",
    "\ud800", "x" * 513, "",
])
def test_trace_cannot_supply_untrusted_header_bytes(trace):
    config = EngineClientConfig(base_url="http://skeleton:8001", service_token=TOKEN)
    client = EngineClient(config)
    with pytest.raises(EngineProtocolError):
        client._headers(trace_id=trace)


def test_ambient_proxy_is_explicitly_disabled_for_canonical_engine(monkeypatch):
    called = {}
    real_client = httpx.AsyncClient

    class CapturingClient(real_client):
        def __init__(self, *args, **kwargs):
            called["trust_env"] = kwargs.get("trust_env")
            called["follow_redirects"] = kwargs.get("follow_redirects")
            super().__init__(*args, **kwargs)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "skeleton"
        assert request.url.path == "/api/v1/engine/providers"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert request.headers["x-zaibatsu-attester"] == "codedock-backend"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv("HTTP_PROXY", "http://evil.example:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://evil.example:3128")
    monkeypatch.setenv("ALL_PROXY", "http://evil.example:3128")
    monkeypatch.setattr(engine.httpx, "AsyncClient", CapturingClient)

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001", service_token=TOKEN),
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(client._request("GET", "/providers"))
    assert result == {"ok": True}
    assert called == {"trust_env": False, "follow_redirects": False}


def test_engine_environment_never_accepts_url_embedded_userinfo(monkeypatch):
    monkeypatch.setenv("SKELETON_INTERNAL_URL", "https://expected.example@evil.example")
    monkeypatch.setenv("SKL_ENGINE_SERVICE_TOKEN", TOKEN)
    with pytest.raises(EngineProtocolError, match="origin"):
        EngineClient.from_env()


def test_response_is_not_followed_across_authentication_domain():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "skeleton"
        return httpx.Response(302, headers={"location": "https://evil.example/collect"})

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001", service_token=TOKEN),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EngineProtocolError, match="non-success"):
        asyncio.run(client._request("GET", "/providers"))
