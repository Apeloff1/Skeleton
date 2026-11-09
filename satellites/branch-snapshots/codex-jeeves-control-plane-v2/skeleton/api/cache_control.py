"""HTTP cache-control helpers for API responses.

Routes hand-build cache headers badly; the helper emits `Cache-Control`,
`ETag`, and `Vary` consistently for GET responses, with a simple
`no-store / private / public` profile switch.

- :class:`CacheProfile` — named, cache-control header value
- :func:`etag_for` — content-hash based ETag builder
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class CachePolicy(str, Enum):
    NO_STORE = "no-store"
    PRIVATE = "private, max-age=60"
    PUBLIC = "public, max-age=300"


@dataclass(frozen=True)
class CacheProfile:
    name: str
    header: str


DEFAULT_PROFILES = {
    "no-store": CacheProfile("no-store", "no-store"),
    "private": CacheProfile("private", "private, max-age=60"),
    "public": CacheProfile("public", "public, max-age=300"),
}


def headers_for(profile: str, *, etag: Optional[str] = None) -> Dict[str, str]:
    selected = DEFAULT_PROFILES.get(profile)
    value = selected.header if selected else "no-store"
    out = {"Cache-Control": value, "Vary": "Accept, Accept-Encoding"}
    if etag:
        out["ETag"] = etag
    return out


def etag_for(content: str | bytes) -> str:
    raw = content.encode() if isinstance(content, str) else content
    return f'W/"{hashlib.sha256(raw).hexdigest()[:16]}"'
