"""API idempotency — safe retries for POST endpoints.

Clients retry; the API must not double-execute. Idempotency keys map a
client-sent key to the first response, and replays return the stored
payload instead of rerunning the handler.

- :class:`IdempotencyKey` — parsed header (with length/format checks)
- :class:`IdempotencyStore` — TTL-keyed response cache
- :func:`extract_key` / :class:`IdempotencyGuard` — FastAPI integration:
  parse the ``X-Idempotency-Key`` header and short-circuit replays with
  the recorded payload (see ``skeleton/api/routes.py`` forge endpoints).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from skeleton.api.middleware import MiddlewareError

IDEMPOTENCY_HEADER = "X-Idempotency-Key"


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


def extract_key(headers: Dict[str, str]) -> Optional[IdempotencyKey]:
    """Pull the idempotency key from a request header mapping (any casing)."""
    for name, value in headers.items():
        if name.lower() == IDEMPOTENCY_HEADER.lower():
            return parse_key(value)
    return None


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


class IdempotencyGuard:
    """Per-route guard: first execution runs, replays return the recording.

    Usage inside a route handler::

        guard = IdempotencyGuard(_IDEMPOTENCY_STORE)
        replay = guard.replay(headers)
        if replay is not None:
            return replay
        response = {...}  # real work
        guard.remember(headers, response)
        return response
    """

    def __init__(self, store: Optional[IdempotencyStore] = None) -> None:
        self.store = store or IdempotencyStore()

    def replay(self, headers: Dict[str, str]) -> Optional[object]:
        key = extract_key(headers)
        if key is None:
            return None
        return self.store.seen(key)

    def remember(self, headers: Dict[str, str], response: object) -> None:
        key = extract_key(headers)
        if key is not None:
            self.store.record(key, response)
