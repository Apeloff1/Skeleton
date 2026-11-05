"""Canonical engine delegated credentials are bound to an explicit origin.

All regressions run with MockTransport and no external service.
"""
from __future__ import annotations

import httpx
import pytest

from core import engine_client as engine


_TOKEN = "service-contract-test-" + ("x" * 32)


@pytest.mark.parametrize("url", [
    "http://user:pass@skeleton:8001",
    "http://user@skeleton:8001",
    "https://username:token@engine.example",
    "http://skeleton:8001/api",
    "http://skeleton:8001/api/v1/engine",
    "http://skeleton:8001?token=secret",
    "http://skeleton:8001?",
    "http://skeleton:8001#frag",
    "http://skeleton:8001#",
    "http://skeleton:8001\\@evil.example",
    "http://skeleton:8001\nx-header: injection",
    "http://skeleton:8001\tother",
    "http://skeleton:8001\r\nextra: header",
    "http://skeleton:99999",
    "http://skeleton:abc",
    "http://skeleton:0",
    "http://skeleton:8001//",
    "http://%73keleton:8001",
    "http://.skeleton",
    "http://skeleton..internal",
    "http://skeleton.",
    "http://[::1",
    "file:///tmp/skeleton.sock",
    "javascript://skeleton",
    "//skeleton:8001",
    "http://",
    "http:// ",
])
def test_base_url_rejects_ambiguous_or_auth_bearing_authority(url):
    with pytest.raises(engine.EngineProtocolError, match="base_url"):
        engine.EngineClientConfig(base_url=url, service_token=_TOKEN)


@pytest.mark.parametrize("base,expected", [
    ("http://skeleton:8001", "http://skeleton:8001"),
    ("http://skeleton:8001/", "http://skeleton:8001"),
    ("http://engine", "http://engine"),
    ("https://engine.internal:8443", "https://engine.internal:8443"),
    ("http://127.0.0.1:8001", "http://127.0.0.1:8001"),
    ("http://[::1]:8001", "http://[::1]:8001"),
])
def test_canonical_docker_loopback_and_tls_origins_remain_valid(base, expected):
    cfg = engine.EngineClientConfig(base_url=base, service_token=_TOKEN)
    assert cfg.base_url == expected
    assert cfg.service_token == _TOKEN


def test_environment_rejects_url_credentials_before_engine_connect(monkeypatch):
    monkeypatch.setenv("SKELETON_INTERNAL_URL", "http://alice:secret@attacker.internal")
    monkeypatch.setenv("SKL_ENGINE_SERVICE_TOKEN", _TOKEN)
    with pytest.raises(engine.EngineProtocolError, match="base_url"):
        engine.EngineClient.from_env()


@pytest.mark.asyncio
async def test_engine_transport_does_not_inherit_proxy_or_redirect_settings(monkeypatch):
    calls = []
    requests = []
    original_factory = engine.httpx.AsyncClient

    def traced_async_client(*args, **kwargs):
        calls.append(dict(kwargs))
        return original_factory(*args, **kwargs)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setattr(engine.httpx, "AsyncClient", traced_async_client)
    client = engine.EngineClient(
        engine.EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_TOKEN,
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(engine.EngineNotFoundError):
        await client.status(
            "exec-origin-test",
            actor_id="actor-origin",
            tenant_id="tenant-origin",
        )
    assert len(calls) == 1
    assert calls[0]["trust_env"] is False
    assert calls[0]["follow_redirects"] is False
    assert requests and requests[0].url.host == "skeleton"
    assert requests[0].url.port == 8001
    assert requests[0].headers["authorization"] == "Bearer " + _TOKEN
    assert "/api/v1/engine/" in requests[0].url.path
