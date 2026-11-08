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



@pytest.mark.parametrize("value", [
    "value\nx-forwarded-host: evil.example",
    "abc\r\nAuthorization: other",
    "subj\tb",
    "unicode-🔑",
    "x" * 513,
])
def test_service_principal_header_rejected_at_config_boundary(value):
    with pytest.raises(engine.EngineProtocolError, match="service_principal"):
        engine.EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_TOKEN,
            service_principal=value,
        )


@pytest.mark.parametrize("token", [
    "x" * 31, "x" * 4097, "x" * 32 + "\n", "x" * 32 + "\r",
    "x" * 16 + " " + "x" * 16, "🔑" * 32,
])
def test_service_token_must_be_printable_ascii_without_whitespace(token):
    with pytest.raises(engine.EngineProtocolError, match="service token"):
        engine.EngineClientConfig(base_url="http://skeleton:8001", service_token=token)


@pytest.mark.asyncio
@pytest.mark.parametrize("trace", [
    "trace\nAuthorization: Bearer attacker",
    "trace\r\nHost: attacker.example",
    "\u2028separator",
    "trace\tinvalid",
])
async def test_invalid_trace_header_rejected_without_network_calls(trace):
    connected = []
    async def handler(request):
        connected.append(request)
        return httpx.Response(200, json={})
    client = engine.EngineClient(
        engine.EngineClientConfig(base_url="http://skeleton:8001", service_token=_TOKEN),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(engine.EngineProtocolError, match="trace_id"):
        await client.status(
            "exec-header-test", actor_id="actor", tenant_id="tenant", trace_id=trace,
        )
    assert connected == []


@pytest.mark.parametrize("timeout", [10 ** 1000, 1e999, float("inf"), float("nan")])
def test_engine_timeout_nonfinite_or_overflow_fails_before_transport(timeout):
    with pytest.raises(engine.EngineProtocolError):
        engine.EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_TOKEN,
            request_timeout_s=timeout,
        )


def test_positive_finite_timeout_preserves_existing_contract():
    config = engine.EngineClientConfig(
        base_url="http://skeleton:8001",
        service_token=_TOKEN,
        request_timeout_s=15.0,
    )
    assert config.request_timeout_s == 15.0



@pytest.mark.parametrize("setting,value", [
    ("SKELETON_INTERNAL_URL", " http://skeleton:8001"),
    ("SKELETON_INTERNAL_URL", "http://skeleton:8001 "),
    ("SKELETON_INTERNAL_URL", "http://skeleton:8001\n"),
    ("SKL_ENGINE_SERVICE_TOKEN", _TOKEN + " "),
    ("SKL_ENGINE_SERVICE_TOKEN", "\n" + _TOKEN),
    ("SKL_ENGINE_SERVICE_TOKEN", _TOKEN + "\r"),
    ("SKL_ENGINE_SERVICE_PRINCIPAL", "operator\nInjected: header"),
    ("SKL_ENGINE_SERVICE_PRINCIPAL", " operator"),
])
def test_operator_environment_never_normalizes_malformed_engine_authority(
    monkeypatch, setting, value,
):
    monkeypatch.setenv("SKELETON_INTERNAL_URL", "http://skeleton:8001")
    monkeypatch.setenv("SKL_ENGINE_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("SKL_ENGINE_SERVICE_PRINCIPAL", "codedock-backend")
    monkeypatch.setenv(setting, value)
    with pytest.raises(engine.EngineProtocolError):
        engine.EngineClientConfig.from_env()


def test_normalized_operator_environment_still_produces_exact_origin(monkeypatch):
    monkeypatch.setenv("SKELETON_INTERNAL_URL", "http://skeleton:8001/")
    monkeypatch.setenv("SKL_ENGINE_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("SKL_ENGINE_SERVICE_PRINCIPAL", "codedock-backend")
    result = engine.EngineClientConfig.from_env()
    assert result is not None
    assert result.base_url == "http://skeleton:8001"
    assert result.service_token == _TOKEN
    assert result.service_principal == "codedock-backend"
