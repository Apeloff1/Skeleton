"""Bounded paged KV-cache control plane.

This module stores opaque key/value cache payloads behind model-, adapter- and
namespace-scoped prefix identities. It does not assume a tensor framework. The
caller owns physical KV tensors; this control plane owns safe prefix reuse,
page-aligned lookup, TTL expiry, LRU eviction and memory accounting.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Iterable, Sequence


_MAX_TOKEN_ID = (1 << 63) - 1


@dataclass(frozen=True)
class KVCacheKey:
    """Isolation-safe identity for one cached prefix checkpoint."""

    namespace: str
    model_id: str
    adapter_id: str
    token_count: int
    prefix_digest: str


@dataclass(frozen=True)
class KVCacheHit:
    """A successful cache lookup."""

    key: KVCacheKey
    value: Any
    matched_tokens: int
    exact: bool
    hits: int


@dataclass
class _Entry:
    key: KVCacheKey
    value: Any
    size_bytes: int
    created_at: float
    last_access: float
    hits: int = 0


class PagedKVCache:
    """Thread-safe prefix cache with bounded entries and optional byte budget.

    Longest-prefix lookup only considers page boundaries plus the exact input
    length. This keeps lookup work linear in token count and prevents an
    accidental O(n^2) hash/search loop on long contexts.
    """

    def __init__(
        self,
        *,
        max_entries: int = 2048,
        max_bytes: int | None = None,
        page_size_tokens: int = 128,
        ttl_seconds: float | None = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if max_bytes is not None and max_bytes <= 0:
            raise ValueError("max_bytes must be positive when set")
        if page_size_tokens <= 0:
            raise ValueError("page_size_tokens must be positive")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive when set")

        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.page_size_tokens = page_size_tokens
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[KVCacheKey, _Entry] = OrderedDict()
        self._bytes = 0
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expired = 0

    def put(
        self,
        model_id: str,
        token_ids: Sequence[int],
        value: Any,
        *,
        namespace: str = "default",
        adapter_id: str = "",
        size_bytes: int = 0,
    ) -> KVCacheKey:
        """Insert or replace one prefix checkpoint and return its stable key."""

        tokens = self._normalize_tokens(token_ids)
        self._validate_scope(namespace, model_id)
        if size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        if self.max_bytes is not None and size_bytes > self.max_bytes:
            raise ValueError("entry exceeds cache byte budget")

        key = KVCacheKey(
            namespace=namespace,
            model_id=model_id,
            adapter_id=adapter_id,
            token_count=len(tokens),
            prefix_digest=self._digest(tokens),
        )
        now = self._clock()

        with self._lock:
            self._prune_expired_locked(now)
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._bytes -= previous.size_bytes
            self._entries[key] = _Entry(
                key=key,
                value=value,
                size_bytes=size_bytes,
                created_at=now,
                last_access=now,
            )
            self._bytes += size_bytes
            self._evict_to_budget_locked()
        return key

    def get_exact(
        self,
        model_id: str,
        token_ids: Sequence[int],
        *,
        namespace: str = "default",
        adapter_id: str = "",
    ) -> KVCacheHit | None:
        """Return an exact-prefix hit, isolated by namespace/model/adapter."""

        tokens = self._normalize_tokens(token_ids)
        self._validate_scope(namespace, model_id)
        key = KVCacheKey(namespace, model_id, adapter_id, len(tokens), self._digest(tokens))
        return self._lookup_key(key, exact=True)

    def get_longest_prefix(
        self,
        model_id: str,
        token_ids: Sequence[int],
        *,
        namespace: str = "default",
        adapter_id: str = "",
    ) -> KVCacheHit | None:
        """Return the longest reusable page-aligned prefix or exact checkpoint."""

        tokens = self._normalize_tokens(token_ids)
        self._validate_scope(namespace, model_id)
        candidates = self._prefix_candidates(tokens)
        now = self._clock()

        with self._lock:
            for token_count, digest in reversed(candidates):
                key = KVCacheKey(namespace, model_id, adapter_id, token_count, digest)
                entry = self._entries.get(key)
                if entry is None:
                    continue
                if self._is_expired(entry, now):
                    self._remove_locked(key, expired=True)
                    continue
                entry.hits += 1
                entry.last_access = now
                self._entries.move_to_end(key)
                self._hits += 1
                return KVCacheHit(
                    key=key,
                    value=entry.value,
                    matched_tokens=token_count,
                    exact=token_count == len(tokens),
                    hits=entry.hits,
                )
            self._misses += 1
            return None

    def invalidate(
        self,
        *,
        namespace: str | None = None,
        model_id: str | None = None,
        adapter_id: str | None = None,
    ) -> int:
        """Invalidate entries matching every supplied scope selector."""

        removed = 0
        with self._lock:
            for key in list(self._entries):
                if namespace is not None and key.namespace != namespace:
                    continue
                if model_id is not None and key.model_id != model_id:
                    continue
                if adapter_id is not None and key.adapter_id != adapter_id:
                    continue
                self._remove_locked(key)
                removed += 1
        return removed

    def prune_expired(self) -> int:
        """Remove stale entries and return how many were reclaimed."""

        with self._lock:
            before = len(self._entries)
            self._prune_expired_locked(self._clock())
            return before - len(self._entries)

    def clear(self) -> int:
        """Remove every entry and return the previous entry count."""

        return self.invalidate()

    def stats(self) -> dict[str, int | float | None]:
        """Return operational counters without exposing cache keys or payloads."""

        with self._lock:
            self._prune_expired_locked(self._clock())
            return {
                "entries": len(self._entries),
                "bytes": self._bytes,
                "max_entries": self.max_entries,
                "max_bytes": self.max_bytes,
                "page_size_tokens": self.page_size_tokens,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "expired": self._expired,
            }

    def _lookup_key(self, key: KVCacheKey, *, exact: bool) -> KVCacheHit | None:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if self._is_expired(entry, now):
                self._remove_locked(key, expired=True)
                self._misses += 1
                return None
            entry.hits += 1
            entry.last_access = now
            self._entries.move_to_end(key)
            self._hits += 1
            return KVCacheHit(
                key=key,
                value=entry.value,
                matched_tokens=key.token_count,
                exact=exact,
                hits=entry.hits,
            )

    def _evict_to_budget_locked(self) -> None:
        while len(self._entries) > self.max_entries or (
            self.max_bytes is not None and self._bytes > self.max_bytes
        ):
            key = next(iter(self._entries))
            self._remove_locked(key)
            self._evictions += 1

    def _prune_expired_locked(self, now: float) -> None:
        if self.ttl_seconds is None:
            return
        for key, entry in list(self._entries.items()):
            if self._is_expired(entry, now):
                self._remove_locked(key, expired=True)

    def _remove_locked(self, key: KVCacheKey, *, expired: bool = False) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return
        self._bytes -= entry.size_bytes
        if expired:
            self._expired += 1

    def _is_expired(self, entry: _Entry, now: float) -> bool:
        return self.ttl_seconds is not None and now - entry.created_at >= self.ttl_seconds

    def _prefix_candidates(self, tokens: tuple[int, ...]) -> list[tuple[int, str]]:
        hasher = hashlib.blake2b(digest_size=16, person=b"SkeletonKVCache")
        candidates: list[tuple[int, str]] = []
        total = len(tokens)
        for index, token in enumerate(tokens, start=1):
            hasher.update(token.to_bytes(8, "big", signed=False))
            if index % self.page_size_tokens == 0 or index == total:
                candidates.append((index, hasher.hexdigest()))
        return candidates

    @staticmethod
    def _digest(tokens: Iterable[int]) -> str:
        hasher = hashlib.blake2b(digest_size=16, person=b"SkeletonKVCache")
        for token in tokens:
            hasher.update(token.to_bytes(8, "big", signed=False))
        return hasher.hexdigest()

    @staticmethod
    def _normalize_tokens(token_ids: Sequence[int]) -> tuple[int, ...]:
        if not token_ids:
            raise ValueError("token_ids cannot be empty")
        normalized: list[int] = []
        for token in token_ids:
            if isinstance(token, bool) or not isinstance(token, int):
                raise TypeError("token_ids must contain integers")
            if token < 0 or token > _MAX_TOKEN_ID:
                raise ValueError("token id must fit an unsigned 63-bit integer")
            normalized.append(token)
        return tuple(normalized)

    @staticmethod
    def _validate_scope(namespace: str, model_id: str) -> None:
        if not namespace:
            raise ValueError("namespace cannot be empty")
        if not model_id:
            raise ValueError("model_id cannot be empty")


KVCache = PagedKVCache

__all__ = ["KVCache", "KVCacheHit", "KVCacheKey", "PagedKVCache"]
