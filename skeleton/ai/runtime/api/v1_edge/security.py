"""Security headers and strict-allowlist CORS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

DEFAULT_SECURITY_HEADERS: Dict[str, str] = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "cache-control": "no-store",
    "cross-origin-resource-policy": "same-origin",
}


@dataclass(frozen=True)
class CorsPolicy:
    origins: FrozenSet[str] = frozenset()
    methods: Tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE")
    headers: Tuple[str, ...] = ("authorization", "content-type", "idempotency-key", "x-api-key", "x-request-id", "traceparent")
    allow_credentials: bool = False
    max_age: int = 600

    def __post_init__(self):
        if "*" in self.origins and self.allow_credentials:
            raise ValueError("wildcard origin cannot be combined with credentials")

    def allowed(self, origin: Optional[str]) -> bool:
        return bool(origin) and ("*" in self.origins or origin in self.origins)

    def response_headers(self, origin: str) -> Dict[str, str]:
        h = {"access-control-allow-origin": "*" if "*" in self.origins and not self.allow_credentials else origin,
             "vary": "Origin",
             "access-control-expose-headers": "x-request-id, traceparent, retry-after, ratelimit-remaining"}
        if self.allow_credentials:
            h["access-control-allow-credentials"] = "true"
        return h

    def preflight_headers(self, origin: str, req_method: Optional[str], req_headers: Optional[str]) -> Optional[Dict[str, str]]:
        if not self.allowed(origin) or (req_method or "").upper() not in self.methods:
            return None
        if req_headers:
            asked = {h.strip().lower() for h in req_headers.split(",") if h.strip()}
            if not asked <= set(self.headers):
                return None
        h = self.response_headers(origin)
        h.update({"access-control-allow-methods": ", ".join(self.methods),
                  "access-control-allow-headers": ", ".join(self.headers),
                  "access-control-max-age": str(self.max_age)})
        return h
