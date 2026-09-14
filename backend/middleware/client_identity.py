"""Security primitives for client identity and request correlation.

Forwarding headers are attacker-controlled unless the immediate peer is a
trusted reverse proxy. This module centralises that trust boundary so rate
limits, audit logs, and access logs agree on the same client identity.

The default is deliberately fail-closed: no proxy network is trusted unless
TRUSTED_PROXY_CIDRS is configured explicitly by the deployment.
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

# Never trust forwarding headers implicitly. A deployment behind a known
# ingress must opt in with the ingress' exact CIDR(s), e.g. 10.0.0.0/24.
_DEFAULT_TRUSTED_PROXY_CIDRS = ""
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# Forwarded headers are attacker-influenced even when they arrive through a
# trusted proxy. Bound both total work and chain depth to avoid turning client
# identity extraction into a CPU/memory amplification primitive.
_MAX_FORWARDED_FOR_CHARS = 4096
_MAX_FORWARDED_HOPS = 32


def _parse_ip(value: str | None, *, allow_zone: bool = False) -> IPAddress | None:
    if not value:
        return None
    value = value.strip().strip("[]")
    if not value:
        return None

    # ASGI peer addresses may legitimately contain an IPv6 zone identifier.
    # Forwarded values may not: accepting zones there creates multiple textual
    # identities for the same address and can weaken per-client controls.
    if "%" in value:
        if not allow_zone:
            return None
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
    TRUSTED_PROXY_CIDRS. The chain is walked right-to-left, discarding trusted
    hops until the nearest untrusted address is found.

    Oversized, over-deep, or malformed forwarding data fails closed to the
    immediate peer rather than consuming unbounded work or becoming an
    attacker-controlled identity string.
    """
    peer = _parse_ip(peer_host, allow_zone=True)
    if peer is None:
        return "unknown"

    networks = tuple(trusted_networks) if trusted_networks is not None else parse_trusted_proxy_cidrs()
    if not forwarded_for or not _is_trusted(peer, networks):
        return peer.compressed

    if len(forwarded_for) > _MAX_FORWARDED_FOR_CHARS:
        return peer.compressed

    raw_hops = forwarded_for.split(",")
    if len(raw_hops) > _MAX_FORWARDED_HOPS:
        return peer.compressed

    chain: list[IPAddress] = []
    for raw_hop in raw_hops:
        hop = _parse_ip(raw_hop)
        if hop is None:
            # Do not silently delete malformed elements from a trusted chain:
            # doing so can alter hop ordering and make a different address look
            # authoritative. Treat the entire header as untrusted instead.
            return peer.compressed
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
