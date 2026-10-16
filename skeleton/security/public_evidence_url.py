"""Offline, fail-closed public HTTPS citation *format* validation.

This is never proof that a source exists, is independent, has been fetched,
or is trustworthy. Actual network access must use the separately governed
outbound HTTP resolver with DNS/peer/redirect controls.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


_DISALLOWED_SUFFIXES = (
    ".localhost", ".local", ".internal", ".test",
    ".invalid", ".example", ".onion", ".home.arpa",
)
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class PublicEvidenceURLError(ValueError):
    """Source citation cannot qualify as a public HTTPS locator."""


def validate_public_evidence_url(value: object) -> str:
    """Return an unchanged canonical-looking HTTPS locator or refuse it.

    No network request, DNS lookup, or redirect following is performed.
    """
    if (not isinstance(value, str) or not value or len(value) > 1024
            or value != value.strip() or "\\" in value
            or any(ord(char) < 33 or ord(char) == 127 for char in value)):
        raise PublicEvidenceURLError("invalid public evidence URL")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise PublicEvidenceURLError("malformed evidence URL") from exc
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or parsed.fragment
            or parsed.query.startswith("#")):
        raise PublicEvidenceURLError("evidence URL requires public HTTPS without credentials or fragments")
    if parsed.netloc.endswith(".") or "%" in parsed.netloc:
        raise PublicEvidenceURLError("ambiguous encoded or trailing-dot host")
    if port not in (None, 443):
        raise PublicEvidenceURLError("nonstandard evidence port not allowed")
    if host.startswith("[") or host.endswith("]"):
        raise PublicEvidenceURLError("malformed evidence hostname")
    # Reject Unicode confusables unless the caller has explicitly converted
    # the domain through their trusted IDNA registration process.
    try:
        host.encode("ascii", "strict")
    except UnicodeError as exc:
        raise PublicEvidenceURLError("non-ASCII evidence host") from exc
    host = host.lower()
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        if not addr.is_global:
            raise PublicEvidenceURLError("private, loopback or reserved IP evidence URL")
    else:
        if (host in {"localhost", "metadata.google.internal"}
                or host.endswith(_DISALLOWED_SUFFIXES)
                or host.count(".") < 1 or len(host) > 253
                or not all(_LABEL.fullmatch(part) for part in host.split("."))):
            raise PublicEvidenceURLError("non-public or malformed evidence hostname")
        # Numeric alternate host spellings can be parsed as IPv4 by HTTP clients:
        # e.g. 2130706433 or 0177.0.0.1. Exclude these entirely.
        if all(c.isdigit() or c == "." for c in host):
            raise PublicEvidenceURLError("ambiguous numeric evidence hostname")
    return value
