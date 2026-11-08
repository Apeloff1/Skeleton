"""Network-bound regression tests for external room API DNS rebinding defenses."""
from __future__ import annotations

import socket
from types import SimpleNamespace

import httpx
import pytest

from gameforge.rooms import room_api_gateway as gateway


def _record(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    address = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)


@pytest.mark.asyncio
async def test_api_connects_only_to_resolved_public_ip_with_original_host_and_sni(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.com"}))
    calls = []
    monkeypatch.setattr(gateway.socket, "getaddrinfo",
                        lambda *args, **kwargs: [_record("93.184.216.34")])

    class RecordingClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def request(self, method, path, **kwargs):
            calls.append(("request", method, path, kwargs))
            return SimpleNamespace(text="ok", is_success=True, status_code=200)

    monkeypatch.setattr(httpx, "AsyncClient", RecordingClient)
    result = await gateway._api_query({
        "url": "https://api.example.com/v1?q=hello",
        "headers": {"X-Trace": "safe"},
    })
    assert result["ok"] is True
    _, client = calls[0]
    assert client["base_url"] == "https://93.184.216.34"
    assert client["follow_redirects"] is False
    assert client["trust_env"] is False
    _, method, path, kwargs = calls[1]
    assert method == "GET"
    assert path == "/v1?q=hello"
    assert kwargs["headers"]["Host"] == "api.example.com"
    assert kwargs["headers"]["X-Trace"] == "safe"
    assert kwargs["extensions"] == {"sni_hostname": "api.example.com"}


@pytest.mark.asyncio
async def test_rebinding_to_private_ip_on_second_resolution_fails_closed(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(gateway, "_EXTERNAL_API_HOSTS", frozenset({"api.example.com"}))
    answers = iter([[_record("93.184.216.34")], [_record("127.0.0.1")]])
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *args, **kwargs: next(answers))

    class MustNotConnect:
        def __init__(self, **kwargs):
            raise AssertionError("private DNS rebinding was accepted")

    monkeypatch.setattr(httpx, "AsyncClient", MustNotConnect)
    result = await gateway._api_query({"url": "https://api.example.com/path"})
    assert result["ok"] is False
    assert result["error"] == "api_query_failed"


@pytest.mark.parametrize("answers", [
    [_record("93.184.216.34"), _record("10.1.2.3")],
    [_record("127.0.0.2")],
    [_record("::1")],
    [_record("fc00::1")],
])
def test_mixed_or_private_dns_addresses_are_rejected(monkeypatch, answers):
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *args, **kwargs: answers)
    with pytest.raises(ValueError, match="non-public"):
        gateway._resolve_public_host("api.example.com")


def test_pinned_ipv6_origin_preserves_bracketed_authority(monkeypatch):
    monkeypatch.setattr(gateway.socket, "getaddrinfo",
                        lambda *args, **kwargs: [_record("2606:2800:220:1:248:1893:25c8:1946")])
    ip = gateway._resolve_public_host("api.example.com")
    assert gateway._origin_for_host(ip) == "https://[2606:2800:220:1:248:1893:25c8:1946]"
