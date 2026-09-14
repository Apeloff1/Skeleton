"""Trusted client-IP resolution for HTTP middleware.

Never trust forwarding headers merely because they are present.  A request may
supply ``X-Forwarded-For`` itself, so the header is considered only when the
immediate TCP peer belongs to an explicitly trusted proxy network.

Configure trusted ingress/load-balancer networks with ``TRUSTED_PROXY_CIDRS``.
The conservative default trusts loopback only, which is appropriate for local
reverse proxies and fails closed everywhere else.
"""
from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Iterable

from starlette.requests import Request

_DEFAULT_TRUSTED_PROXY_CIDRS = "127.0.0.0/8,::1/128"


def _split_cidrs(raw: str) -> Iterable[str]:
    for value in raw.split(","):
        value = value.strip()
        if value:
            yield value


@lru_cache(maxsize=8)
def _trusted_networks(raw: str) -> tuple[ipaddress._BaseNetwork, ...]:
    networks: list[ipaddress._BaseNetwork] = []
    for value in _split_cidrs(raw):
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            # Invalid configuration must not widen trust. Ignore the bad entry
            # and continue with the remaining explicitly valid networks.
            continue
    return tuple(networks)


def trusted_proxy_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    raw = os.environ.get("TRUSTED_PROXY_CIDRS", _DEFAULT_TRUSTED_PROXY_CIDRS)
    return _trusted_networks(raw)


def _parse_ip(value: str) -> ipaddress._BaseAddress | None:
    value = value.strip()
    if not value:
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_trusted_proxy(address: ipaddress._BaseAddress) -> bool:
    return any(address in network for network in trusted_proxy_networks())


def resolve_client_ip(request: Request, *, unknown: str = "-") -> str:
    """Return the authenticated network peer/client address for ``request``.

    ``X-Forwarded-For`` is used only when the socket peer is a configured
    trusted proxy.  The chain is walked from right to left and stops at the
    first untrusted hop.  Any malformed forwarded address causes a fail-closed
    fallback to the immediate peer rather than accepting attacker-controlled
    text as an identity.
    """
    peer_text = request.client.host if request.client else ""
    peer = _parse_ip(peer_text)
    if peer is None:
        return peer_text or unknown

    if not _is_trusted_proxy(peer):
        return peer.compressed

    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return peer.compressed

    forwarded: list[ipaddress._BaseAddress] = []
    for value in xff.split(","):
        parsed = _parse_ip(value)
        if parsed is None:
            return peer.compressed
        forwarded.append(parsed)

    current = peer
    for candidate in reversed(forwarded):
        if not _is_trusted_proxy(current):
            break
        current = candidate

    return current.compressed
