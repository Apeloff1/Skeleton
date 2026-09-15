"""Focused regressions for adversarial middleware squash deltas."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware


def _request(*, peer: str, xff: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", xff.encode("ascii"))],
            "client": (peer, 43210),
            "server": ("testserver", 80),
        }
    )


def test_forwarded_chain_over_hop_budget_fails_closed_to_peer(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    chain = ",".join(f"198.51.100.{(index % 250) + 1}" for index in range(33))
    request = _request(peer="10.0.0.10", xff=chain)

    assert api_middleware._client_ip(request) == "10.0.0.10"


def test_rate_limit_telemetry_does_not_disclose_proxy_allowlist(monkeypatch) -> None:
    networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("2001:db8::/32"),
    )
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", networks)

    rate_limit = api_middleware.get_stats()["rate_limit"]

    assert rate_limit["trusted_proxy_count"] == 2
    assert "trusted_proxy_cidrs" not in rate_limit
