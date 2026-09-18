"""Fail-closed validation helpers for outbound HTTPS destinations.

This module deliberately handles the deterministic URL and literal-address
portion of SSRF policy. Network clients that perform DNS resolution must also
re-check resolved addresses at connect time; syntax validation alone cannot
eliminate DNS-rebinding races.
"""

from __future__ import annotations

from ipaddress import ip_address
import socket
from urllib.parse import urlsplit

_MAX_OUTBOUND_URL_LENGTH = 2048
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
        "metadata.azure.internal",
        "instance-data.ec2.internal",
    }
)
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
)


def _literal_ip(host: str):
    """Parse canonical and legacy IPv4 spellings without DNS resolution."""
    try:
        return ip_address(host)
    except ValueError:
        pass
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ip_address(packed)


def _is_public_unicast(address) -> bool:
    """Return True only for globally routable unicast addresses."""
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not getattr(address, "is_site_local", False)
    )


def validate_public_https_url(url: str, *, purpose: str = "outbound URL") -> tuple[str, str]:
    """Validate a user-controlled outbound destination and return URL + host.

    The policy requires HTTPS, rejects credentials, fragments, local/internal
    hostnames, ambiguous single-label names, control characters, overlong URLs,
    and every literal address that is not globally routable unicast.
    """
    if not isinstance(url, str):
        raise ValueError(f"{purpose} must be a string")

    value = url.strip()
    if (
        not value
        or len(value) > _MAX_OUTBOUND_URL_LENGTH
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"invalid {purpose}")

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"invalid {purpose}") from exc

    if parsed.scheme.lower() != "https":
        raise ValueError(f"{purpose} must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{purpose} must not contain credentials")
    if parsed.fragment:
        raise ValueError(f"{purpose} must not contain a fragment")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"{purpose} must include a hostname")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{purpose} has invalid port") from exc

    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError(f"{purpose} has invalid hostname") from exc

    literal = _literal_ip(normalized_host)
    if literal is None:
        if (
            normalized_host in _BLOCKED_HOSTS
            or normalized_host.endswith(_BLOCKED_SUFFIXES)
            or "." not in normalized_host
        ):
            raise ValueError(f"{purpose} targets a blocked local endpoint")
    elif not _is_public_unicast(literal):
        raise ValueError(f"{purpose} targets a non-public IP address")

    return value, normalized_host
