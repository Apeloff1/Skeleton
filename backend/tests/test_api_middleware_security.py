"""Security regression tests for API middleware trust boundaries."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware


def _request(client_host: str, *, xff: str | None = None, request_id: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/test",
        "raw_path": b"/api/test",
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 43210),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _trust(monkeypatch, *cidrs: str) -> None:
    networks = tuple(ipaddress.ip_network(value) for value in cidrs)
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", networks)


def test_untrusted_peer_cannot_spoof_rate_limit_identity(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("198.51.100.24", xff="203.0.113.99")

    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_trusted_proxy_uses_nearest_untrusted_forwarded_hop(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request(
        "10.0.0.5",
        xff="198.51.100.24, 203.0.113.7",
    )

    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_leftmost_xff_spoof_does_not_override_real_client(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request(
        "10.0.0.5",
        xff="192.0.2.250, 198.51.100.24",
    )

    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_malformed_forwarded_chain_falls_back_to_peer(monkeypatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="198.51.100.24, not-an-ip")

    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_request_id_accepts_only_bounded_header_safe_values() -> None:
    accepted = _request("198.51.100.24", request_id="trace-01.prod:abc_123")
    rejected = _request("198.51.100.24", request_id="unsafe value with spaces")
    oversized = _request("198.51.100.24", request_id="a" * 129)

    assert api_middleware._request_id(accepted) == "trace-01.prod:abc_123"
    assert api_middleware._request_id(rejected) != "unsafe value with spaces"
    assert len(api_middleware._request_id(oversized)) == 16
