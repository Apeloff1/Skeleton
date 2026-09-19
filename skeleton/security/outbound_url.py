"""Fail-closed validation helpers for outbound HTTPS destinations.

Syntax validation is only the first SSRF boundary. Hostnames are resolved to a
bounded set of public unicast addresses before use, redirect destinations are
revalidated, and callers can verify the peer address observed at connection
time against the approved resolution snapshot. This closes the common
"dns-name looked public, socket connected private" rebinding gap when clients
wire the peer check into their transport.

The helpers do not open sockets. They produce and validate authority evidence
that a network client can enforce at its own connect boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
import socket
from typing import Callable, Iterable, Sequence
from urllib.parse import SplitResult, urlsplit

_MAX_OUTBOUND_URL_LENGTH = 2048
_MAX_RESOLVED_ADDRESSES = 16
_DEFAULT_HTTPS_PORT = 443
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

Address = IPv4Address | IPv6Address
Resolver = Callable[..., Sequence[tuple[int, int, int, str, tuple[object, ...]]]]


@dataclass(frozen=True, slots=True)
class ResolvedDestination:
    """Immutable DNS authority snapshot for one validated HTTPS destination."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.addresses:
            raise ValueError("resolved destination must contain at least one address")
        canonical: list[str] = []
        for raw in self.addresses:
            address = ip_address(raw)
            if not _is_public_unicast(address):
                raise ValueError("resolved destination contains a non-public address")
            canonical.append(address.compressed)
        if len(canonical) != len(set(canonical)):
            raise ValueError("resolved destination contains duplicate addresses")
        object.__setattr__(self, "addresses", tuple(sorted(canonical)))


def _literal_ip(host: str) -> Address | None:
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


def _is_public_unicast(address: Address) -> bool:
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


def _parse_validated(url: str, *, purpose: str) -> tuple[str, str, SplitResult]:
    if not isinstance(url, str):
        raise ValueError(f"{purpose} must be a string")

    value = url.strip()
    if (
        not value
        or value != url
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
    if not parsed.netloc:
        raise ValueError(f"{purpose} must include an authority")

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

    return value, normalized_host, parsed


def validate_public_https_url(
    url: str,
    *,
    purpose: str = "outbound URL",
) -> tuple[str, str]:
    """Validate the deterministic portion of an outbound HTTPS destination.

    The policy requires HTTPS and rejects credentials, fragments, local or
    internal hostnames, ambiguous single-label names, control characters,
    overlong URLs, and every literal address that is not globally routable
    unicast.
    """

    value, normalized_host, _ = _parse_validated(url, purpose=purpose)
    return value, normalized_host


def resolve_public_https_url(
    url: str,
    *,
    purpose: str = "outbound URL",
    resolver: Resolver = socket.getaddrinfo,
    max_addresses: int = _MAX_RESOLVED_ADDRESSES,
) -> ResolvedDestination:
    """Resolve a validated HTTPS URL and reject any non-public DNS answer.

    Mixed public/private answers fail closed. The entire bounded answer set is
    captured so the transport can later verify the actual connected peer.
    """

    if isinstance(max_addresses, bool) or not isinstance(max_addresses, int):
        raise ValueError("max_addresses must be an integer")
    if not 1 <= max_addresses <= _MAX_RESOLVED_ADDRESSES:
        raise ValueError(
            f"max_addresses must be between 1 and {_MAX_RESOLVED_ADDRESSES}"
        )

    value, host, parsed = _parse_validated(url, purpose=purpose)
    port = parsed.port or _DEFAULT_HTTPS_PORT

    literal = _literal_ip(host)
    if literal is not None:
        return ResolvedDestination(
            url=value,
            host=host,
            port=port,
            addresses=(literal.compressed,),
        )

    try:
        answers = resolver(
            host,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{purpose} DNS resolution failed") from exc

    if not isinstance(answers, Sequence):
        try:
            answers = tuple(answers)
        except TypeError as exc:
            raise ValueError(f"{purpose} DNS resolution returned invalid evidence") from exc

    if not answers:
        raise ValueError(f"{purpose} DNS resolution returned no addresses")
    if len(answers) > max_addresses:
        raise ValueError(f"{purpose} DNS resolution exceeded address bound")

    resolved: list[str] = []
    for answer in answers:
        if not isinstance(answer, tuple) or len(answer) < 5:
            raise ValueError(f"{purpose} DNS resolution returned malformed evidence")
        sockaddr = answer[4]
        if not isinstance(sockaddr, tuple) or not sockaddr:
            raise ValueError(f"{purpose} DNS resolution returned malformed socket address")
        raw_address = sockaddr[0]
        if not isinstance(raw_address, str):
            raise ValueError(f"{purpose} DNS resolution returned non-text address")
        try:
            address = ip_address(raw_address)
        except ValueError as exc:
            raise ValueError(f"{purpose} DNS resolution returned invalid address") from exc
        if not _is_public_unicast(address):
            raise ValueError(f"{purpose} DNS resolution includes non-public address")
        resolved.append(address.compressed)

    canonical = tuple(sorted(set(resolved)))
    if not canonical:
        raise ValueError(f"{purpose} DNS resolution returned no usable addresses")
    if len(canonical) > max_addresses:
        raise ValueError(f"{purpose} DNS resolution exceeded address bound")

    return ResolvedDestination(
        url=value,
        host=host,
        port=port,
        addresses=canonical,
    )


def validate_connected_peer(
    destination: ResolvedDestination,
    peer_address: str,
    *,
    purpose: str = "outbound peer",
) -> str:
    """Verify the connected peer remains inside the approved DNS snapshot.

    A caller should invoke this after connection establishment (or in a custom
    transport callback) using the numeric peer address returned by the socket.
    """

    if not isinstance(destination, ResolvedDestination):
        raise TypeError("destination must be ResolvedDestination")
    if not isinstance(peer_address, str):
        raise ValueError(f"{purpose} address must be a string")
    try:
        peer = ip_address(peer_address)
    except ValueError as exc:
        raise ValueError(f"{purpose} address is invalid") from exc
    if not _is_public_unicast(peer):
        raise ValueError(f"{purpose} is not public unicast")
    canonical = peer.compressed
    if canonical not in destination.addresses:
        raise ValueError(f"{purpose} does not match approved DNS evidence")
    return canonical


def validate_public_https_redirect(
    source_url: str,
    destination_url: str,
    *,
    purpose: str = "redirect destination",
    allow_cross_origin: bool = False,
) -> tuple[str, str]:
    """Revalidate an HTTPS redirect and optionally require the same origin.

    Redirects are never trusted merely because the original URL was approved.
    By default both hostname and effective port must remain unchanged.
    """

    _, source_host, source = _parse_validated(source_url, purpose="redirect source")
    destination_value, destination_host, destination = _parse_validated(
        destination_url,
        purpose=purpose,
    )

    if not allow_cross_origin:
        source_port = source.port or _DEFAULT_HTTPS_PORT
        destination_port = destination.port or _DEFAULT_HTTPS_PORT
        if (
            not hmac_compare_host(source_host, destination_host)
            or source_port != destination_port
        ):
            raise ValueError(f"{purpose} changes origin")

    return destination_value, destination_host


def hmac_compare_host(left: str, right: str) -> bool:
    """Constant-time-ish equality helper for canonical ASCII hostnames.

    Hostnames are public data, so timing is not a confidentiality boundary; the
    helper exists mainly to keep equality semantics exact and centralized.
    """

    import hmac

    return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))


def validate_resolution_set(
    addresses: Iterable[str],
    *,
    purpose: str = "resolved destination",
    max_addresses: int = _MAX_RESOLVED_ADDRESSES,
) -> tuple[str, ...]:
    """Validate pre-resolved addresses supplied by a custom transport."""

    materialized = tuple(addresses)
    if not materialized:
        raise ValueError(f"{purpose} contains no addresses")
    if len(materialized) > max_addresses:
        raise ValueError(f"{purpose} exceeds address bound")
    canonical: set[str] = set()
    for raw in materialized:
        if not isinstance(raw, str):
            raise ValueError(f"{purpose} contains a non-text address")
        try:
            address = ip_address(raw)
        except ValueError as exc:
            raise ValueError(f"{purpose} contains an invalid address") from exc
        if not _is_public_unicast(address):
            raise ValueError(f"{purpose} contains a non-public address")
        canonical.add(address.compressed)
    if len(canonical) > max_addresses:
        raise ValueError(f"{purpose} exceeds address bound")
    return tuple(sorted(canonical))


__all__ = [
    "ResolvedDestination",
    "resolve_public_https_url",
    "validate_connected_peer",
    "validate_public_https_redirect",
    "validate_public_https_url",
    "validate_resolution_set",
]
