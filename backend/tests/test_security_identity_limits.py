from __future__ import annotations

from middleware.client_identity import extract_client_ip, parse_trusted_proxy_cidrs


def _trusted():
    return parse_trusted_proxy_cidrs("10.0.0.0/8")


def test_forwarded_chain_over_depth_limit_fails_closed_to_peer() -> None:
    header = ",".join(["203.0.113.7"] * 33)
    assert extract_client_ip("10.0.0.10", header, _trusted()) == "10.0.0.10"


def test_forwarded_header_over_size_limit_fails_closed_to_peer() -> None:
    header = "203.0.113.7," + (" " * 4096)
    assert extract_client_ip("10.0.0.10", header, _trusted()) == "10.0.0.10"


def test_malformed_hop_invalidates_entire_forwarded_chain() -> None:
    header = "203.0.113.7, definitely-not-an-ip, 10.0.0.20"
    assert extract_client_ip("10.0.0.10", header, _trusted()) == "10.0.0.10"


def test_ipv6_zone_identifier_is_rejected_in_forwarded_header() -> None:
    assert extract_client_ip("10.0.0.10", "fe80::1%eth0", _trusted()) == "10.0.0.10"


def test_peer_ipv6_zone_identifier_is_normalized() -> None:
    assert extract_client_ip("fe80::1%eth0", None, ()) == "fe80::1"
