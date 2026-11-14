"""Identity header hygiene for traffic crossing the systems edge.

Callers must never be able to assert identity with a plain header, and the
verified principal must never leak back out to clients. Inbound, every
header in :data:`SPOOFABLE_IDENTITY_HEADERS` (and any ``x-skeleton-*``
header) is dropped before the request reaches a system; the edge then
adds exactly one trusted ``x-skeleton-caller`` (service name only, never
scopes or key ids) and ``x-skeleton-system``. Outbound, the same identity
headers are stripped from responses so the principal stays inside the
platform.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

CALLER_HEADER = "x-skeleton-caller"
SYSTEM_HEADER = "x-skeleton-system"
DEADLINE_HEADER = "x-skeleton-deadline-ms"
REQUEST_ID_HEADER = "x-request-id"

SPOOFABLE_IDENTITY_HEADERS: frozenset[str] = frozenset({
    "x-principal",
    "x-principal-id",
    "x-service",
    "x-service-name",
    "x-service-identity",
    "x-caller",
    "x-caller-service",
    "x-user",
    "x-user-id",
    "x-forwarded-user",
    "x-forwarded-email",
    "x-forwarded-preferred-username",
    "x-remote-user",
    "remote-user",
    "x-auth-request-user",
    "x-auth-request-email",
    "x-authenticated-user",
    "x-authenticated-userid",
    "x-authenticated-service",
    "x-client-cert-subject",
    "x-ssl-client-s-dn",
    "x-scopes",
    "x-granted-scopes",
})

_PREFIXES: Tuple[str, ...] = ("x-skeleton-", "x-authenticated-", "x-auth-request-")
_RESPONSE_LEAK_HEADERS: frozenset[str] = frozenset({
    CALLER_HEADER, "x-principal", "x-principal-id", "x-service-identity", "x-authenticated-service",
    "x-scopes", "x-granted-scopes", "x-service-token",
})
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

RawHeaders = List[Tuple[bytes, bytes]]


def is_identity_header(name: str) -> bool:
    low = name.lower()
    return low in SPOOFABLE_IDENTITY_HEADERS or low.startswith(_PREFIXES)


def scrub_request_headers(raw: Iterable[Tuple[bytes, bytes]]) -> Tuple[RawHeaders, List[str]]:
    """Drop identity headers; return (kept, dropped_names_sorted_unique)."""
    kept: RawHeaders = []
    dropped: set[str] = set()
    for k, v in raw:
        name = k.decode("latin-1")
        if is_identity_header(name):
            dropped.add(name.lower())
            continue
        kept.append((k, v))
    return kept, sorted(dropped)


def scrub_response_headers(raw: Iterable[Tuple[bytes, bytes]]) -> Tuple[RawHeaders, List[str]]:
    kept: RawHeaders = []
    dropped: set[str] = set()
    for k, v in raw:
        low = k.decode("latin-1").lower()
        if low in _RESPONSE_LEAK_HEADERS or low.startswith("x-skeleton-caller"):
            dropped.add(low)
            continue
        kept.append((k, v))
    return kept, sorted(dropped)


def _safe_value(value: str) -> bytes:
    v = "".join(ch for ch in str(value) if 0x20 <= ord(ch) < 0x7F)
    return v[:128].encode("latin-1")


def trusted_headers(
    *,
    system: str,
    caller: Optional[str],
    deadline_ms: Optional[int] = None,
) -> RawHeaders:
    out: RawHeaders = [(SYSTEM_HEADER.encode(), _safe_value(system))]
    out.append((CALLER_HEADER.encode(), _safe_value(caller if caller else "anonymous")))
    if deadline_ms is not None:
        out.append((DEADLINE_HEADER.encode(), str(max(0, int(deadline_ms))).encode()))
    return out


def header_value(raw: Sequence[Tuple[bytes, bytes]], name: str) -> Optional[str]:
    low = name.lower().encode("latin-1")
    for k, v in raw:
        if k.lower() == low:
            return v.decode("latin-1")
    return None


def header_values(raw: Sequence[Tuple[bytes, bytes]], name: str) -> List[str]:
    low = name.lower().encode("latin-1")
    return [v.decode("latin-1") for k, v in raw if k.lower() == low]


def valid_request_id(value: Optional[str]) -> bool:
    return bool(value) and bool(_REQUEST_ID_RE.match(value or ""))


__all__ = [
    "CALLER_HEADER",
    "DEADLINE_HEADER",
    "REQUEST_ID_HEADER",
    "SPOOFABLE_IDENTITY_HEADERS",
    "SYSTEM_HEADER",
    "header_value",
    "header_values",
    "is_identity_header",
    "scrub_request_headers",
    "scrub_response_headers",
    "trusted_headers",
    "valid_request_id",
]
