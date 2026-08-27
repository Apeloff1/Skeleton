"""API idempotency — safe retries for POST endpoints.

Clients retry; the API must not double-execute. Idempotency keys map a
client-sent key to the first response, and replays return the stored
payload instead of rerunning the handler.

- :class:`IdempotencyKey` — parsed header (with length/format checks)
- :class:`IdempotencyStore` — TTL-keyed response cache
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from skeleton.api.middleware import MiddlewareError


class IdempotencyError(MiddlewareError):
    code = "API.IDEMPOTENCY"


@dataclass(frozen=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) > 128:
            raise IdempotencyError("invalid idempotency key")


def parse_key(header: Optional[str]) -> Optional[IdempotencyKey]:
    if header is None:
        return None
    return IdempotencyKey(value=header.strip())


class IdempotencyStore:
    """TTL store mapping key -> recorded response payload."""

    def __init__(self, *, ttl_s: float = 3600.0) -> None:
        self.ttl_s = ttl_s
        self._entries: Dict[str, Tuple[float, object]] = {}

    def seen(self, key: IdempotencyKey) -> Optional[object]:
        entry = self._entries.get(key.value)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= time.monotonic():
            del self._entries[key.value]
            return None
        return payload

    def record(self, key: IdempotencyKey, response: object) -> None:
        self._entries[key.value] = (
            time.monotonic() + self.ttl_s,
            response,
        )

    def size(self) -> int:
        return len(self._entries)
