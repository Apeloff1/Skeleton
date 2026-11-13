"""Idempotency keys for unsafe requests (POST).

Semantics (aligned with draft-ietf-httpapi-idempotency-key-header):
  * same key + same request fingerprint -> stored response is replayed;
  * same key + different fingerprint -> CORE.IDEMPOTENCY.KEY_REUSED (409);
  * a concurrent request holding the key -> CORE.IDEMPOTENCY.IN_FLIGHT (409);
  * keys expire after ``ttl_seconds`` and are scoped per (tenant, actor, route).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .clock import Clock
from .errors import conflict, validation

KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")
DEFAULT_TTL = 24 * 3600.0
LOCK_SECONDS = 60.0


@dataclass(frozen=True)
class StoredResponse:
    status: int
    body: Any


@dataclass(frozen=True)
class IdempotencyRecord:
    scope_key: str
    fingerprint: str
    response: StoredResponse | None
    locked_until: float
    expires_at: float


class IdempotencyStore(Protocol):
    def get(self, scope_key: str) -> IdempotencyRecord | None: ...
    def try_lock(self, record: IdempotencyRecord, now: float) -> bool:
        """Insert the record, or take over an expired/unlocked-without-response one."""
    def save_response(self, scope_key: str, response: StoredResponse) -> None: ...
    def release(self, scope_key: str) -> None: ...


def fingerprint(method: str, route: str, body: Any) -> str:
    raw = json.dumps([method.upper(), route, body], sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def scope_key(tenant_id: str, actor_id: str, route: str, key: str) -> str:
    parts = (tenant_id, actor_id, route, key)
    if any(type(value) is not str or not value or len(value) > 512 for value in parts):
        raise validation("CORE.IDEMPOTENCY.INVALID_SCOPE", "idempotency scope is invalid")
    # Unambiguous tuple serialization prevents cross-tenant collisions when
    # trusted identifiers contain delimiters used by older concatenation.
    return json.dumps(parts, separators=(",", ":"), ensure_ascii=True)


class Idempotency:
    def __init__(self, store: IdempotencyStore, clock: Clock, ttl_seconds: float = DEFAULT_TTL) -> None:
        self.store, self.clock, self.ttl = store, clock, ttl_seconds

    def run(self, key: str | None, skey_parts: tuple[str, str, str], fp: str,
            action: Callable[[], StoredResponse]) -> tuple[StoredResponse, bool]:
        """Execute ``action`` at most once per key. Returns (response, replayed)."""
        if key is None:
            return action(), False
        if type(key) is not str or not KEY_RE.fullmatch(key):
            raise validation("CORE.IDEMPOTENCY.INVALID_KEY", "Idempotency-Key is malformed")
        skey = scope_key(*skey_parts, key)
        now = self.clock.now()
        existing = self.store.get(skey)
        if existing and existing.expires_at > now:
            if existing.fingerprint != fp:
                raise conflict("CORE.IDEMPOTENCY.KEY_REUSED",
                               "Idempotency-Key was used with a different request")
            if existing.response is not None:
                return existing.response, True
            if existing.locked_until > now:
                raise conflict("CORE.IDEMPOTENCY.IN_FLIGHT",
                               "a request with this Idempotency-Key is in progress")
        rec = IdempotencyRecord(skey, fp, None, now + LOCK_SECONDS, now + self.ttl)
        if not self.store.try_lock(rec, now):
            raise conflict("CORE.IDEMPOTENCY.IN_FLIGHT",
                           "a request with this Idempotency-Key is in progress")
        try:
            resp = action()
        except BaseException:
            self.store.release(skey)
            raise
        if resp.status < 500:
            self.store.save_response(skey, resp)
        else:
            self.store.release(skey)
        return resp, False
