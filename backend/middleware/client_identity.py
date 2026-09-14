"""Security primitives for client identity and request correlation.

Forwarding headers are attacker-controlled unless the immediate peer is a
trusted reverse proxy.  This module centralises that trust boundary so rate
limits, audit logs, and access logs agree on the same client identity.
"""
from __future__ import annotations

import ipaddress
import os
import re
import uuid
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network

_DEFAULT_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    value = value.strip().strip("[]")
    # ASGI servers expose host and port separately, but tolerate an IPv6 zone
    # identifier if a platform passes one through.
    value = value.split("%", 1)[0]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def parse_trusted_proxy_cidrs(raw: str | None = None) -> tuple[IPNetwork, ...]:
    """Parse trusted proxy networks, ignoring invalid entries fail-closed."""
    if raw is None:
        raw = os.environ.get("TRUSTED_PROXY_CIDRS", _DEFAULT_TRUSTED_PROXY_CIDRS)
    networks: list[IPNetwork] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # Invalid trust configuration must never broaden trust.
            continue
    return tuple(networks)


def _is_trusted(ip: IPAddress, networks: Iterable[IPNetwork]) -> bool:
    return any(ip.version == network.version and ip in network for network in networks)


def extract_client_ip(
    peer_host: str | None,
    forwarded_for: str | None,
    trusted_networks: Iterable[IPNetwork] | None = None,
) -> str:
    """Return the defensible client IP for a request.

    X-Forwarded-For is considered only when the immediate ASGI peer belongs to
    TRUSTED_PROXY_CIDRS.  The chain is then walked right-to-left, discarding
    trusted hops until the nearest untrusted address is found.  Malformed
    forwarded entries are ignored rather than accepted as identity strings.
    """
    peer = _parse_ip(peer_host)
    if peer is None:
        return "unknown"

    networks = tuple(trusted_networks) if trusted_networks is not None else parse_trusted_proxy_cidrs()
    if not forwarded_for or not _is_trusted(peer, networks):
        return peer.compressed

    chain: list[IPAddress] = []
    for raw_hop in forwarded_for.split(","):
        hop = _parse_ip(raw_hop)
        if hop is not None:
            chain.append(hop)

    # Include the immediate peer so the algorithm is explicit about the full
    # proxy chain, then select the nearest hop outside our trust boundary.
    chain.append(peer)
    for hop in reversed(chain):
        if not _is_trusted(hop, networks):
            return hop.compressed
    return peer.compressed


def client_ip(request) -> str:
    """Extract a request client IP without trusting arbitrary proxy headers."""
    peer_host = request.client.host if request.client else None
    return extract_client_ip(peer_host, request.headers.get("x-forwarded-for"))


def sanitize_request_id(value: str | None) -> str:
    """Accept compact printable correlation IDs; replace everything else."""
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex
