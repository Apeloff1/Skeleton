"""Adversarial regression coverage for trusted-proxy client identity."""

from __future__ import annotations

import asyncio
import ipaddress

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from api_middleware import RateLimiterMiddleware


def _request(
    client_host: str,
    *,
    xff: str | list[str] | None = None,
    request_id: str | None = "proxy-test",
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        values = [xff] if isinstance(xff, str) else xff
        headers.extend((b"x-forwarded-for", value.encode("latin-1")) for value in values)
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))
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
            "client": (client_host, 43210),
            "server": ("testserver", 80),
        }
    )


def _trust(monkeypatch: pytest.MonkeyPatch, *cidrs: str) -> None:
    networks = tuple(ipaddress.ip_network(value) for value in cidrs)
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", networks)


def test_untrusted_peer_cannot_spoof_client_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("198.51.100.24", xff="203.0.113.99")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_trusted_proxy_uses_nearest_untrusted_forwarded_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request("10.0.0.5", xff="198.51.100.24, 203.0.113.7")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_leftmost_spoof_does_not_override_nearest_untrusted_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="192.0.2.250, 198.51.100.24")
    assert api_middleware._client_ip(request) == "198.51.100.24"


def test_malformed_forwarded_chain_fails_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff="198.51.100.24, not-an-ip")
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_all_trusted_forwarded_hops_fail_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "203.0.113.0/24")
    request = _request("10.0.0.5", xff="203.0.113.7")
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_duplicate_xff_headers_fail_closed_to_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    request = _request("10.0.0.5", xff=["198.51.100.24", "192.0.2.44"])
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_excessive_forwarded_hops_fail_closed_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    chain = ",".join(f"198.51.100.{(index % 250) + 1}" for index in range(33))
    request = _request("10.0.0.5", xff=chain)
    assert api_middleware._client_ip(request) == "10.0.0.5"


def test_ipv6_proxy_chain_is_canonical_and_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    _trust(monkeypatch, "2001:db8:1::/48")
    request = _request("2001:db8:1::5", xff="2001:db8:2::42")
    assert api_middleware._client_ip(request) == "2001:db8:2::42"


def test_invalid_trusted_proxy_config_fails_closed_without_echoing_value() -> None:
    bad_value = "definitely-not-a-network"
    with pytest.raises(ValueError) as exc_info:
        api_middleware._parse_trusted_proxy_networks(bad_value)
    assert bad_value not in str(exc_info.value)


def test_telemetry_does_not_publish_trusted_proxy_cidrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8", "2001:db8::/32")
    rate_limit_stats = api_middleware.get_stats()["rate_limit"]
    assert rate_limit_stats["trusted_proxy_count"] == 2
    assert "trusted_proxy_cidrs" not in rate_limit_stats


def test_untrusted_xff_rotation_cannot_rotate_rate_limit_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, "10.0.0.0/8")
    limiter = RateLimiterMiddleware(object(), per_minute=1, burst=1)
    first = _request("198.51.100.24", xff="203.0.113.1")
    second = _request("198.51.100.24", xff="203.0.113.2")

    async def downstream(_request: Request) -> Response:
        return Response(status_code=200)

    first_response = asyncio.run(limiter.dispatch(first, downstream))
    second_response = asyncio.run(limiter.dispatch(second, downstream))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert set(limiter._buckets) == {"198.51.100.24"}
