"""Residual adversarial coverage for API proxy identity metadata."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware


def _request(client_host: str, xff: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", xff.encode("latin-1"))],
            "client": (client_host, 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def test_forwarded_chain_is_bounded_before_address_parsing(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    overlong = ",".join(
        f"192.0.2.{index % 250 + 1}" for index in range(api_middleware._MAX_XFF_HOPS + 1)
    )
    request = _request("10.0.0.10", overlong)
    assert api_middleware._client_ip(request) == "10.0.0.10"


def test_forwarded_chain_at_bound_still_resolves_nearest_untrusted(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    values = ["203.0.113.7"] + [
        f"10.0.0.{index}" for index in range(1, api_middleware._MAX_XFF_HOPS)
    ]
    request = _request("10.0.0.250", ",".join(values))
    assert api_middleware._client_ip(request) == "203.0.113.7"


def test_telemetry_reports_proxy_count_without_disclosing_allowlist(monkeypatch) -> None:
    networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("2001:db8::/32"),
    )
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", networks)
    rate_limit = api_middleware.get_stats()["rate_limit"]

    assert rate_limit["trusted_proxy_count"] == 2
    assert "trusted_proxy_cidrs" not in rate_limit
    rendered = repr(rate_limit)
    assert "10.0.0.0/8" not in rendered
    assert "2001:db8::/32" not in rendered
