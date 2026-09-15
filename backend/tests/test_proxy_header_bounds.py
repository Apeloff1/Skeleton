"""Focused bounds and disclosure tests for trusted proxy metadata."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware


def _request(client_host: str, xff: str) -> Request:
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
            "client": (client_host, 43210),
            "server": ("testserver", 80),
        }
    )


def test_xff_chain_has_hard_hop_bound(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )
    peer = "10.0.0.5"
    within_bound = ",".join(f"198.51.100.{index}" for index in range(1, 33))
    over_bound = within_bound + ",198.51.100.33"

    assert api_middleware._client_ip(_request(peer, within_bound)) == "198.51.100.32"
    assert api_middleware._client_ip(_request(peer, over_bound)) == peer


def test_telemetry_reports_proxy_count_without_disclosing_networks(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("2001:db8::/32"),
        ),
    )
    stats = api_middleware.get_stats()["rate_limit"]

    assert stats["trusted_proxy_count"] == 2
    assert "trusted_proxy_cidrs" not in stats
    assert "10.0.0.0/8" not in repr(stats)
    assert "2001:db8::/32" not in repr(stats)
