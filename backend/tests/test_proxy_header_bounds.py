"""Focused bounds and disclosure tests for trusted proxy metadata."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

import api_middleware
import middleware.security as legacy_security


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


def _trusted_test_networks():
    return (ipaddress.ip_network("10.0.0.0/8"),)


def _trust_test_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        _trusted_test_networks(),
    )


def test_xff_chain_has_hard_hop_bound(monkeypatch) -> None:
    _trust_test_proxy(monkeypatch)
    trusted = _trusted_test_networks()
    peer = "10.0.0.5"
    within_bound = ",".join(f"198.51.100.{index}" for index in range(1, 33))
    over_bound = within_bound + ",198.51.100.33"

    request = _request(peer, within_bound)
    assert api_middleware._client_ip(request) == "198.51.100.32"
    assert legacy_security._client_ip(request, trusted) == "198.51.100.32"

    request = _request(peer, over_bound)
    assert api_middleware._client_ip(request) == peer
    assert legacy_security._client_ip(request, trusted) == peer


def test_xff_value_has_hard_character_bound_before_ip_parsing(monkeypatch) -> None:
    _trust_test_proxy(monkeypatch)
    trusted = _trusted_test_networks()
    peer = "10.0.0.5"
    original_primary = api_middleware._canonical_ip
    original_legacy = legacy_security._canonical_ip

    def guarded_primary_canonical_ip(value: str):
        if len(value) > 1000:
            raise AssertionError("oversized forwarded value reached the primary IP parser")
        return original_primary(value)

    def guarded_legacy_canonical_ip(value: str):
        if len(value) > 1000:
            raise AssertionError("oversized forwarded value reached the legacy IP parser")
        return original_legacy(value)

    monkeypatch.setattr(api_middleware, "_canonical_ip", guarded_primary_canonical_ip)
    monkeypatch.setattr(legacy_security, "_canonical_ip", guarded_legacy_canonical_ip)
    oversized = "1" * (api_middleware._MAX_XFF_CHARS + 1)

    request = _request(peer, oversized)
    assert api_middleware._client_ip(request) == peer
    assert legacy_security._client_ip(request, trusted) == peer


def test_proxy_bounds_stay_aligned_between_active_security_stacks() -> None:
    assert legacy_security._MAX_XFF_HOPS == api_middleware._MAX_XFF_HOPS
    assert legacy_security._MAX_XFF_CHARS == api_middleware._MAX_XFF_CHARS


def test_malformed_proxy_cidr_disables_trust_in_both_active_stacks() -> None:
    raw = "10.0.0.0/8, definitely-not-a-cidr, 2001:db8::/32"

    assert api_middleware._parse_trusted_proxy_networks(raw) == ()
    assert legacy_security._parse_trusted_proxy_networks(raw) == ()


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
