"""Idempotency registry for model planning requests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class AIIdempotencyRecord:
    key: str
    request_digest: str
    proposal_fingerprint: str
    created_at: float
    expires_at: float


class AIIdempotencyConflict(RuntimeError):
    pass


class AIIdempotencyRegistry:
    def __init__(
        self,
        *,
        max_items: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._clock = clock
        self._items: dict[str, AIIdempotencyRecord] = {}
        self._lock = threading.RLock()

    @staticmethod
    def request_digest(payload: bytes | str) -> str:
        raw = payload if isinstance(payload, bytes) else payload.encode()
        return hashlib.sha256(raw).hexdigest()

    def _prune(self) -> None:
        now = self._clock()
        for key in [
            key for key, item in self._items.items()
            if item.expires_at <= now
        ]:
            del self._items[key]

    def register(
        self,
        key: str,
        *,
        request_digest: str,
        proposal_fingerprint: str,
        ttl_seconds: float = 3600.0,
    ) -> AIIdempotencyRecord:
        if not key or len(key) > 256:
            raise ValueError("invalid AI idempotency key")
        if len(request_digest) != 64 or len(proposal_fingerprint) != 64:
            raise ValueError("AI idempotency digests must be SHA-256 hex")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._prune()
            existing = self._items.get(key)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise AIIdempotencyConflict("idempotency key reused with different request")
                if existing.proposal_fingerprint != proposal_fingerprint:
                    raise AIIdempotencyConflict("idempotency key maps to different proposal")
                return existing
            if len(self._items) >= self.max_items:
                raise RuntimeError("AI idempotency capacity exhausted")
            now = self._clock()
            record = AIIdempotencyRecord(
                key,
                request_digest,
                proposal_fingerprint,
                now,
                now + ttl_seconds,
            )
            self._items[key] = record
            return record

    def get(self, key: str) -> AIIdempotencyRecord | None:
        with self._lock:
            self._prune()
            return self._items.get(key)

    def snapshot(self) -> tuple[AIIdempotencyRecord, ...]:
        with self._lock:
            self._prune()
            return tuple(self._items[key] for key in sorted(self._items))
