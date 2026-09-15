"""Canonical client-IP resolution for HTTP security middleware.

Forwarded headers are attacker-controlled input unless the immediate TCP peer is
an explicitly trusted reverse proxy.  Keep this logic in one module so audit,
rate-limit, and observability layers cannot drift into different trust models.
"""
from __future__ import annotations

import logging
import os
from ipaddress import ip_address, ip_network

from starlette.requests import Request

log = logging.getLogger("api.client_identity")


def _parse_trusted_proxy_networks(raw: str):
    networks = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ip_network(value, strict=False))
        except ValueError:
            # Invalid trust configuration must never broaden trust.
            log.warning("ignoring invalid TRUSTED_PROXIES entry: %r", value)
    return tuple(networks)


TRUSTED_PROXY_NETWORKS = _parse_trusted_proxy_networks(
    os.environ.get("TRUSTED_PROXIES", "")
)


def is_trusted_proxy(host: str) -> bool:
    """Return True only for an IP inside an explicitly configured proxy network."""
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    return any(addr in network for network in TRUSTED_PROXY_NETWORKS)


def resolve_client_ip(request: Request) -> str:
    """Return the security-relevant client IP for a request.

    Rules:
    * Ignore forwarding headers from untrusted immediate peers.
    * If the immediate peer is trusted, validate the complete X-Forwarded-For chain.
    * Walk the chain right-to-left and return the first non-trusted address.
    * Fail closed to the immediate peer when the chain is malformed.

    This supports multiple explicitly trusted proxies while preventing a direct client
    from claiming a loopback/private address to bypass quotas or forge audit records.
    """
    client = request.client
    peer = client.host if client else "unknown"
    if not is_trusted_proxy(peer):
        return peer

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return peer

    values = [value.strip() for value in xff.split(",") if value.strip()]
    if not values:
        return peer

    parsed = []
    for value in values:
        try:
            parsed.append(ip_address(value))
        except ValueError:
            return peer

    for addr in reversed(parsed):
        candidate = str(addr)
        if not is_trusted_proxy(candidate):
            return candidate
    return peer


def trusted_proxy_strings() -> list[str]:
    """Serializable view for diagnostics without exposing mutable config state."""
    return [str(network) for network in TRUSTED_PROXY_NETWORKS]
