"""Regression tests for trusted client-IP resolution and rate-limit identity."""
from __future__ import annotations

from starlette.requests import Request

from api_middleware import RateLimiterMiddleware, _client_ip
from core.client_ip import _trusted_networks, resolve_client_ip


def _request(peer: str, xff: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43210),
            "server": ("testserver", 80),
        }
    )


def _set_trusted_proxies(monkeypatch, value: str) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", value)
    _trusted_networks.cache_clear()


def test_untrusted_peer_cannot_spoof_x_forwarded_for(monkeypatch) -> None:
    _set_trusted_proxies(monkeypatch, "10.0.0.0/8,127.0.0.0/8,::1/128")
    request = _request("198.51.100.23", "203.0.113.9")

    assert resolve_client_ip(request) == "198.51.100.23"


def test_trusted_proxy_chain_resolves_first_untrusted_hop(monkeypatch) -> None:
    _set_trusted_proxies(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.3", "203.0.113.7, 10.0.0.2")

    assert resolve_client_ip(request) == "203.0.113.7"


def test_malformed_forwarded_chain_falls_back_to_immediate_peer(monkeypatch) -> None:
    _set_trusted_proxies(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.3", "203.0.113.7, definitely-not-an-ip")

    assert resolve_client_ip(request) == "10.0.0.3"


def test_ipv6_peer_is_normalized(monkeypatch) -> None:
    _set_trusted_proxies(monkeypatch, "127.0.0.0/8")
    request = _request("2001:0db8:0000:0000:0000:0000:0000:0001", "203.0.113.99")

    assert resolve_client_ip(request) == "2001:db8::1"


def test_spoofed_xff_cannot_rotate_rate_limit_bucket(monkeypatch) -> None:
    _set_trusted_proxies(monkeypatch, "10.0.0.0/8")
    first = _request("198.51.100.23", "203.0.113.1")
    second = _request("198.51.100.23", "203.0.113.2")

    first_ip = _client_ip(first)
    second_ip = _client_ip(second)
    assert first_ip == second_ip == "198.51.100.23"

    async def app(scope, receive, send):
        raise AssertionError("not used")

    limiter = RateLimiterMiddleware(app, per_minute=60, burst=2)
    first_bucket = limiter._bucket_for(first_ip)
    second_bucket = limiter._bucket_for(second_ip)
    assert first_bucket is second_bucket
