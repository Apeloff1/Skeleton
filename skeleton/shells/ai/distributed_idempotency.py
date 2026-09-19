"""Distributed AI planning idempotency registry."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.idempotency import AIIdempotencyConflict, AIIdempotencyRecord
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class DistributedIdempotencyConfig:
    namespace: str = "shell-ai-idempotency"


class DistributedAIIdempotencyRegistry:
    """Globally bind idempotency key to one request/proposal pair."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        config: DistributedIdempotencyConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.backend = backend
        self.config = config or DistributedIdempotencyConfig()
        self._clock = clock
        self._lock = threading.RLock()

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
        existing = self.backend.get(self.config.namespace, key)
        now = self._clock()
        if existing is not None:
            if not isinstance(existing.value, AIIdempotencyRecord):
                raise RuntimeError("distributed idempotency record type mismatch")
            item = existing.value
            if item.expires_at <= now:
                try:
                    self.backend.delete(
                        self.config.namespace,
                        key,
                        expected_revision=existing.revision,
                    )
                except DistributedStateConflict:
                    existing = self.backend.get(self.config.namespace, key)
                    if existing is not None:
                        return self._validate(existing.value, request_digest, proposal_fingerprint)
            else:
                return self._validate(item, request_digest, proposal_fingerprint)
        with self._lock:
            record = AIIdempotencyRecord(
                key,
                request_digest,
                proposal_fingerprint,
                now,
                now + ttl_seconds,
            )
        try:
            self.backend.put_if_absent(
                self.config.namespace,
                key,
                record,
            )
            return record
        except DistributedStateConflict:
            winner = self.backend.get(self.config.namespace, key)
            if winner is None:
                raise AIIdempotencyConflict("idempotency race lost without winner")
            return self._validate(
                winner.value,
                request_digest,
                proposal_fingerprint,
            )

    @staticmethod
    def _validate(
        item: object,
        request_digest: str,
        proposal_fingerprint: str,
    ) -> AIIdempotencyRecord:
        if not isinstance(item, AIIdempotencyRecord):
            raise RuntimeError("distributed idempotency record type mismatch")
        if item.request_digest != request_digest:
            raise AIIdempotencyConflict("idempotency key reused with different request")
        if item.proposal_fingerprint != proposal_fingerprint:
            raise AIIdempotencyConflict("idempotency key maps to different proposal")
        return item

    def get(self, key: str) -> AIIdempotencyRecord | None:
        current = self.backend.get(self.config.namespace, key)
        if current is None:
            return None
        if not isinstance(current.value, AIIdempotencyRecord):
            raise RuntimeError("distributed idempotency record type mismatch")
        if current.value.expires_at <= self._clock():
            try:
                self.backend.delete(
                    self.config.namespace,
                    key,
                    expected_revision=current.revision,
                )
            except DistributedStateConflict:
                pass
            return None
        return current.value
