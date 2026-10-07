"""Metadata-safe cache for reviewed AI plans.

The cache stores typed proposal/review references, not child output or resolved
environment values.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.ai.types import AIPlanProposal


@dataclass(frozen=True)
class CachedAIPlan:
    key: str
    proposal: AIPlanProposal
    policy_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    created_at: float
    expires_at: float
    hits: int = 0

    def valid_for(
        self,
        *,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
        now: float,
    ) -> bool:
        return (
            now < self.expires_at
            and self.policy_fingerprint == policy_fingerprint
            and self.tool_catalog_digest == tool_catalog_digest
            and self.effect_digest == effect_digest
        )


class AIPlanCache:
    def __init__(
        self,
        *,
        max_items: int = 1024,
        default_ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0 or default_ttl_seconds <= 0:
            raise ValueError("AI plan cache limits must be positive")
        self.max_items = max_items
        self.default_ttl_seconds = default_ttl_seconds
        self._clock = clock
        self._items: dict[str, CachedAIPlan] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()

    def _remove(self, key: str) -> None:
        self._items.pop(key, None)
        self._order = [item for item in self._order if item != key]

    def put(
        self,
        key: str,
        proposal: AIPlanProposal,
        *,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
        ttl_seconds: float | None = None,
    ) -> CachedAIPlan:
        if not key or len(key) > 256:
            raise ValueError("invalid AI plan cache key")
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            raise ValueError("AI plan cache TTL must be positive")
        now = self._clock()
        item = CachedAIPlan(
            key,
            proposal,
            policy_fingerprint,
            tool_catalog_digest,
            effect_digest,
            now,
            now + ttl,
        )
        with self._lock:
            self._remove(key)
            self._items[key] = item
            self._order.append(key)
            while len(self._order) > self.max_items:
                self._remove(self._order[0])
            return item

    def get(
        self,
        key: str,
        *,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
    ) -> CachedAIPlan | None:
        now = self._clock()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if not item.valid_for(
                policy_fingerprint=policy_fingerprint,
                tool_catalog_digest=tool_catalog_digest,
                effect_digest=effect_digest,
                now=now,
            ):
                self._remove(key)
                return None
            hit = CachedAIPlan(
                item.key,
                item.proposal,
                item.policy_fingerprint,
                item.tool_catalog_digest,
                item.effect_digest,
                item.created_at,
                item.expires_at,
                item.hits + 1,
            )
            self._items[key] = hit
            self._order = [value for value in self._order if value != key] + [key]
            return hit

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._order.clear()
