"""Network-free regression contracts for catalog HTTPS destination pinning."""
from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from gameforge.knowledge import free_apis


_PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]
_PRIVATE = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))]


@pytest.mark.parametrize("answers", [_PRIVATE, _PUBLIC + _PRIVATE, []])
def test_dns_denies_private_mixed_and_empty(monkeypatch, answers):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo", lambda *_a, **_k: answers)
    with pytest.raises(ValueError):
        free_apis._pin_public_origin("api.github.com")


def test_dns_single_global_ip_is_pinned(monkeypatch):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo", lambda *_a, **_k: _PUBLIC)
    assert free_apis._pin_public_origin("api.github.com") == "https://93.184.216.34"


def test_malformed_dns_record_fails_closed(monkeypatch):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo", lambda *_a, **_k: [(1, 2, 3, "", ())])
    with pytest.raises(ValueError, match="malformed"):
        free_apis._pin_public_origin("api.github.com")


def test_connection_uses_pinned_ip_sni_and_no_proxy(monkeypatch):
    seen = {}
    calls = []
    monkeypatch.setattr(free_apis.socket, "getaddrinfo", lambda host, *args, **kw: calls.append(host) or _PUBLIC)

    class Response:
        status_code = 200
        is_success = True
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b'{"value": 1}'

    class Stream:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *_args):
            return False

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, method, path, **kwargs):
            seen["method"] = method
            seen["path"] = path
            seen["extensions"] = kwargs.get("extensions")
            return Stream()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = asyncio.run(free_apis.fetch("github", {"q": "public"}))
    assert result["ok"] is True
    assert result["data"] == {"value": 1}
    assert seen["base_url"] == "https://93.184.216.34"
    assert seen["headers"]["Host"] == "api.github.com"
    assert seen["extensions"] == {"sni_hostname": "api.github.com"}
    assert seen["follow_redirects"] is False
    assert seen["trust_env"] is False
    assert seen["path"].startswith("/search/repositories?")
    assert calls == ["api.github.com"]


def test_private_dns_stops_before_network_client(monkeypatch):
    monkeypatch.setattr(free_apis.socket, "getaddrinfo", lambda *_a, **_k: _PRIVATE)
    def forbidden(**kwargs):
        raise AssertionError("client constructed after private DNS answer")
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    result = asyncio.run(free_apis.fetch("github", {"q": "x"}))
    assert result["ok"] is False
    assert result["error"] == "api_fetch_failed"
