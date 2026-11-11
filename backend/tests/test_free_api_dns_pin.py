"""Pinned DNS + certificate authority checks for the fixed public knowledge APIs."""
from __future__ import annotations

from contextlib import asynccontextmanager
import socket

import httpx
import pytest

from gameforge.knowledge import free_apis


def _dns(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 443, 0, 0) if family == socket.AF_INET6 else (ip, 443)
    return family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr


@pytest.mark.asyncio
async def test_catalog_egress_pins_public_ip_preserving_host_and_sni(monkeypatch):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo",
                        lambda *args, **kwargs: [_dns("93.184.216.34")])
    calls = []

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 200
        is_success = True

        async def aiter_bytes(self):
            yield b'{"ok":true}'

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def stream(self, method, request_target, **kwargs):
            calls.append(("stream", method, request_target, kwargs))
            yield FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await free_apis.fetch("github", {"q": "safe"})
    assert result["ok"] is True
    assert result["data"] == {"ok": True}
    _, client = calls[0]
    assert client["base_url"] == "https://93.184.216.34"
    assert client["headers"]["Host"] == "api.github.com"
    assert client["trust_env"] is False
    assert client["follow_redirects"] is False
    _, method, target, kwargs = calls[1]
    assert method == "GET"
    assert target.startswith("/search/repositories?")
    assert kwargs["extensions"] == {"sni_hostname": "api.github.com"}


@pytest.mark.asyncio
async def test_catalog_egress_never_connects_to_private_dns(monkeypatch):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo",
                        lambda *args, **kwargs: [_dns("127.0.0.2")])

    class MustNotConnect:
        def __init__(self, **kwargs):
            raise AssertionError("unsafe IP was passed to HTTPX")

    monkeypatch.setattr(httpx, "AsyncClient", MustNotConnect)
    result = await free_apis.fetch("github", {"q": "test"})
    assert result["ok"] is False
    assert result["error"] == "api_fetch_failed"


@pytest.mark.parametrize("answers", [
    [_dns("93.184.216.34"), _dns("10.1.1.1")],
    [_dns("127.0.0.1")],
    [_dns("::1")],
    [_dns("fe80::1")],
])
def test_catalog_dns_rejects_mixed_and_private_answers(monkeypatch, answers):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo",
                        lambda *args, **kwargs: answers)
    with pytest.raises(ValueError, match="non-public"):
        free_apis._pin_public_origin("api.github.com")


def test_catalog_rejects_nonstandard_https_ports_and_fragments():
    api = {"url": "https://api.example.org/query"}
    for url in ["https://api.example.org:444/query", "https://api.example.org/query#frag"]:
        with pytest.raises(ValueError):
            free_apis._catalog_request_parts(api, url)


def test_public_ipv6_address_formats_as_pinned_https_authority(monkeypatch):
    address = "2606:2800:220:1:248:1893:25c8:1946"
    monkeypatch.setattr(
        free_apis.socket, "getaddrinfo",
        lambda *args, **kwargs: [_dns(address)],
    )
    assert free_apis._pin_public_origin("api.github.com") == (
        "https://[2606:2800:220:1:248:1893:25c8:1946]"
    )
