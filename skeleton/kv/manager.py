from __future__ import annotations

import hashlib
import math
import struct
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Sequence

from .types import (
    CacheTier,
    KVCacheConfig,
    KVCacheMatch,
    KVCacheStats,
    KVIntegrityReport,
    KVNamespace,
    KVPageInput,
    KVReuseEstimate,
    KVStorageAdapter,
)


@dataclass(slots=True)
class _Page:
    key: str
    parent_key: str
    namespace_fp: str
    namespace: KVNamespace
    tokens: tuple[int, ...]
    handle: Any
    size_bytes: int
    tier: CacheTier
    recompute_cost: float
    retention_bias: float
    quantization: str
    extra_fingerprint: str
    created_at: float
    last_access: float
    hit_count: int = 0
    pin_count: int = 0


_TIER_WEIGHT = {
    CacheTier.GPU: 1.00,
    CacheTier.CPU: 0.78,
    CacheTier.NVME: 0.48,
    CacheTier.REMOTE: 0.35,
}


class KVCacheManager:
    """Paged, hash-chained KV control plane over opaque backend page handles."""

    def __init__(
        self,
        config: KVCacheConfig | None = None,
        *,
        storage: KVStorageAdapter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or KVCacheConfig()
        self._storage = storage
        self._clock = clock
        self._lock = threading.RLock()
        self._pages: dict[str, _Page] = {}
        self._children: dict[str, set[str]] = defaultdict(set)
        self._namespace_pages: dict[str, set[str]] = defaultdict(set)
        self._trust_bytes: dict[str, int] = defaultdict(int)
        self._frequency: dict[str, int] = defaultdict(int)
        self._ops_since_decay = 0
        self._resident_bytes = 0
        self._counters = defaultdict(int)

    @staticmethod
    def _validate_tokens(tokens: Sequence[int]) -> tuple[int, ...]:
        normalized = tuple(tokens)
        for token in normalized:
            if (
                isinstance(token, bool)
                or not isinstance(token, int)
                or token < 0
                or token > 0xFFFFFFFFFFFFFFFF
            ):
                raise ValueError("token ids must be integers in [0, 2**64 - 1]")
        return normalized

    def _chunks(self, tokens: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
        size = self.config.block_size_tokens
        return tuple(tokens[i : i + size] for i in range(0, len(tokens), size))

    @staticmethod
    def _root(namespace_fp: str) -> str:
        return hashlib.sha256(("root:" + namespace_fp).encode("ascii")).hexdigest()

    @staticmethod
    def _key(namespace_fp: str, parent: str, tokens: tuple[int, ...], extra: str = "") -> str:
        digest = hashlib.sha256()
        digest.update(bytes.fromhex(namespace_fp))
        digest.update(bytes.fromhex(parent))
        digest.update(struct.pack(">I", len(tokens)))
        for token in tokens:
            digest.update(struct.pack(">Q", token))
        encoded = extra.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded)))
        digest.update(encoded)
        return digest.hexdigest()

    def _tick_frequency(self, key: str) -> None:
        self._frequency[key] += 1
        self._ops_since_decay += 1
        if self._ops_since_decay < self.config.frequency_decay_interval:
            return
        self._frequency = defaultdict(
            int,
            ((key, count // 2) for key, count in self._frequency.items() if count > 1),
        )
        self._ops_since_decay = 0

    def _lookup(
        self,
        tokens: tuple[int, ...],
        namespace: KVNamespace,
        *,
        record: bool,
        block_extras: tuple[str, ...] | None,
    ) -> KVCacheMatch:
        namespace_fp = namespace.fingerprint()
        parent = self._root(namespace_fp)
        chunks = self._chunks(tokens)
        extras = block_extras or ("",) * len(chunks)
        if len(extras) != len(chunks):
            raise ValueError(f"expected {len(chunks)} block extras, got {len(extras)}")

        handles: list[Any] = []
        page_keys: list[str] = []
        tiers: list[CacheTier] = []
        matched = 0
        now = self._clock()

        for chunk, extra in zip(chunks, extras):
            key = self._key(namespace_fp, parent, chunk, extra)
            if record:
                self._tick_frequency(key)
            page = self._pages.get(key)
            if page is None:
                break
            if self.config.strict_verification and (
                page.namespace_fp != namespace_fp
                or page.parent_key != parent
                or page.tokens != chunk
                or page.extra_fingerprint != extra
            ):
                self._counters["verification_failures"] += 1
                break
            if record:
                page.last_access = now
                page.hit_count += 1
            handles.append(page.handle)
            page_keys.append(key)
            tiers.append(page.tier)
            matched += len(chunk)
            parent = key

        if matched < self.config.min_prefix_tokens:
            handles.clear()
            page_keys.clear()
            tiers.clear()
            matched = 0

        if record:
            self._counters["lookups"] += 1
            self._counters["token_lookups"] += len(tokens)
            self._counters["token_hits"] += matched
            self._counters["hits"] += int(bool(matched))
            self._counters["full_hits"] += int(bool(tokens) and matched == len(tokens))

        return KVCacheMatch(
            namespace=namespace,
            matched_tokens=matched,
            requested_tokens=len(tokens),
            handles=tuple(handles),
            page_keys=tuple(page_keys),
            tiers=tuple(tiers),
        )

    def lookup(
        self,
        tokens: Sequence[int],
        namespace: KVNamespace,
        *,
        block_extras: Sequence[str] | None = None,
    ) -> KVCacheMatch:
        normalized = self._validate_tokens(tokens)
        extras = tuple(block_extras) if block_extras is not None else None
        with self._lock:
            return self._lookup(normalized, namespace, record=True, block_extras=extras)

    @contextmanager
    def acquire_prefix(
        self,
        tokens: Sequence[int],
        namespace: KVNamespace,
        *,
        block_extras: Sequence[str] | None = None,
    ) -> Iterator[KVCacheMatch]:
        """Atomically look up and pin opaque pages through physical consumption.

        Use this rather than lookup followed by pin when another thread may
        evict or migrate pages. The lease never holds the manager lock while
        the backend consumes the handles. Callers must still authorize the
        namespace before lookup and release physical use before exiting.
        """
        normalized = self._validate_tokens(tokens)
        extras = tuple(block_extras) if block_extras is not None else None
        with self._lock:
            match = self._lookup(normalized, namespace, record=True, block_extras=extras)
            for key in match.page_keys:
                self._pages[key].pin_count += 1
        try:
            yield match
        finally:
            self.release(match.page_keys)

    def _preflight_prefix(
        self, chunks: tuple[tuple[int, ...], ...],
        inputs: tuple[KVPageInput, ...], namespace: KVNamespace, *, pin: bool,
    ) -> None:
        # Validate the complete chain before mutating indexes or releasing any
        # incoming duplicate handles. Pinned admission cannot exceed the hard
        # budgets even when every other resident page is unevictable.
        namespace_fp = namespace.fingerprint()
        parent = self._root(namespace_fp)
        protected = self._pin_protected_keys() if pin else set()
        added = {}
        for chunk, item in zip(chunks, inputs):
            if not isinstance(item, KVPageInput) or not isinstance(item.tier, CacheTier):
                raise ValueError("invalid KV page input or tier")
            key = self._key(namespace_fp, parent, chunk, item.extra_fingerprint)
            existing = self._pages.get(key)
            if existing is not None:
                if (existing.namespace_fp != namespace_fp or existing.parent_key != parent
                        or existing.tokens != chunk or existing.extra_fingerprint != item.extra_fingerprint
                        or existing.quantization != item.quantization):
                    self._counters["verification_failures"] += 1
                    raise RuntimeError("KV cache hash collision or semantic mismatch detected")
                if pin:
                    protected.add(key)
            elif pin:
                added[key] = item.size_bytes
            parent = key
        if not pin:
            return
        protected_bytes = sum(self._pages[key].size_bytes for key in protected)
        domain_bytes = sum(self._pages[key].size_bytes for key in protected
                           if self._pages[key].namespace.trust_domain == namespace.trust_domain)
        new_bytes = sum(added.values())
        limit = self.config.trust_domain_max_bytes
        if (protected_bytes + new_bytes > self.config.max_bytes
                or len(protected) + len(added) > self.config.max_entries
                or (limit is not None and domain_bytes + new_bytes > limit)):
            raise RuntimeError("pinned KV prefix exceeds physical cache budget")

    def estimate_reuse(
        self,
        tokens: Sequence[int],
        namespace: KVNamespace,
        *,
        block_extras: Sequence[str] | None = None,
    ) -> KVReuseEstimate:
        normalized = self._validate_tokens(tokens)
        extras = tuple(block_extras) if block_extras is not None else None
        with self._lock:
            match = self._lookup(normalized, namespace, record=False, block_extras=extras)
            if match.tiers:
                tier_weight = sum(_TIER_WEIGHT[tier] for tier in match.tiers) / len(match.tiers)
                hottest = max(match.tiers, key=_TIER_WEIGHT.__getitem__)
            else:
                tier_weight, hottest = 0.0, None
            return KVReuseEstimate(
                matched_tokens=match.matched_tokens,
                requested_tokens=match.requested_tokens,
                hit_ratio=match.hit_ratio,
                hottest_tier=hottest,
                route_score=match.hit_ratio * tier_weight,
            )

    def commit_prefix(
        self,
        tokens: Sequence[int],
        pages: Sequence[KVPageInput],
        namespace: KVNamespace,
        *,
        pin: bool = False,
    ) -> tuple[str, ...]:
        normalized = self._validate_tokens(tokens)
        chunks = self._chunks(normalized)
        inputs = tuple(pages)
        if not normalized:
            raise ValueError("cannot cache an empty prefix")
        if len(chunks) != len(inputs):
            raise ValueError(
                f"expected {len(chunks)} page handles for {len(normalized)} tokens, got {len(inputs)}"
            )

        namespace_fp = namespace.fingerprint()
        parent = self._root(namespace_fp)
        now = self._clock()
        committed: list[str] = []
        with self._lock:
            self._preflight_prefix(chunks, inputs, namespace, pin=pin)
            for chunk, item in zip(chunks, inputs):
                key = self._key(namespace_fp, parent, chunk, item.extra_fingerprint)
                existing = self._pages.get(key)
                if existing is not None:
                    if (
                        existing.namespace_fp != namespace_fp
                        or existing.parent_key != parent
                        or existing.tokens != chunk
                        or existing.extra_fingerprint != item.extra_fingerprint
                    ):
                        self._counters["verification_failures"] += 1
                        raise RuntimeError("KV cache hash collision or semantic mismatch detected")
                    existing.last_access = now
                    existing.recompute_cost = max(existing.recompute_cost, item.recompute_cost)
                    existing.retention_bias = max(existing.retention_bias, item.retention_bias)
                    existing.pin_count += int(pin)
                    self._release_duplicate(item, existing)
                    self._counters["deduplicated_pages"] += 1
                else:
                    existing = _Page(
                        key=key,
                        parent_key=parent,
                        namespace_fp=namespace_fp,
                        namespace=namespace,
                        tokens=chunk,
                        handle=item.handle,
                        size_bytes=item.size_bytes,
                        tier=item.tier,
                        recompute_cost=item.recompute_cost,
                        retention_bias=item.retention_bias,
                        quantization=item.quantization,
                        extra_fingerprint=item.extra_fingerprint,
                        created_at=now,
                        last_access=now,
                        pin_count=int(pin),
                    )
                    self._pages[key] = existing
                    self._children[parent].add(key)
                    self._namespace_pages[namespace_fp].add(key)
                    self._resident_bytes += item.size_bytes
                    self._trust_bytes[namespace.trust_domain] += item.size_bytes
                    self._counters["stores"] += 1
                committed.append(key)
                parent = key

            self._enforce_limits(namespace.trust_domain)
            return tuple(key for key in committed if key in self._pages)

    def _release_duplicate(self, item: KVPageInput, existing: _Page) -> None:
        if self._storage is None or item.handle is existing.handle:
            return
        try:
            self._storage.release(item.handle, item.tier)
        except Exception:
            self._counters["storage_errors"] += 1

    def transaction(self, namespace: KVNamespace) -> "KVCacheTransaction":
        return KVCacheTransaction(self, namespace)

    def pin(self, page_keys: Iterable[str]) -> None:
        with self._lock:
            for key in page_keys:
                page = self._pages.get(key)
                if page is not None:
                    page.pin_count += 1

    def release(self, page_keys: Iterable[str]) -> None:
        with self._lock:
            for key in page_keys:
                page = self._pages.get(key)
                if page is not None and page.pin_count:
                    page.pin_count -= 1
            self._enforce_limits(None)

    def migrate(self, page_keys: Iterable[str], target: CacheTier) -> tuple[str, ...]:
        if not isinstance(target, CacheTier):
            raise ValueError("invalid cache migration target")
        moved: list[str] = []
        with self._lock:
            protected = self._pin_protected_keys()
            for key in page_keys:
                page = self._pages.get(key)
                if page is None or page.tier == target or key in protected:
                    continue
                if self._storage is None:
                    raise RuntimeError("tier migration requires a KVStorageAdapter")
                page.handle = self._storage.move(page.handle, page.tier, target)
                page.tier = target
                page.last_access = self._clock()
                self._counters["migrations"] += 1
                moved.append(key)
        return tuple(moved)

    def rebalance_local(
        self, *, source: CacheTier, target: CacheTier,
        source_ceiling_bytes: int, target_ceiling_bytes: int,
        max_move_bytes: int, max_pages: int = 128,
        namespace: KVNamespace | None = None,
    ) -> dict[str, int]:
        """Move cold unleased local pages under explicit per-tier budgets.

        Values are logical page-byte accounting, not physical VRAM telemetry.
        A backend must implement move with source custody retained on failure.
        No implicit remote spill, deletion or authority transfer is permitted.
        """
        local = {CacheTier.GPU, CacheTier.CPU, CacheTier.NVME}
        if source not in local or target not in local or source == target:
            raise ValueError("distinct local cache tiers are required")
        for value in (source_ceiling_bytes, target_ceiling_bytes, max_move_bytes):
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                raise ValueError("invalid logical tier byte budget")
        if type(max_pages) is not int or not 1 <= max_pages <= 65536:
            raise ValueError("invalid migration page budget")
        with self._lock:
            if self._storage is None:
                raise RuntimeError("tier migration requires a KVStorageAdapter")
            used_source = sum(p.size_bytes for p in self._pages.values() if p.tier == source)
            used_target = sum(p.size_bytes for p in self._pages.values() if p.tier == target)
            protected = self._pin_protected_keys()
            fingerprint = namespace.fingerprint() if namespace is not None else None
            now = self._clock()
            candidates = sorted(
                (p for p in self._pages.values() if p.tier == source and p.key not in protected
                 and (fingerprint is None or p.namespace_fp == fingerprint)),
                key=lambda p: (self._retention_score(p, now), p.last_access, p.key),
            )
            count = moved_bytes = errors = 0
            for page in candidates:
                if used_source <= source_ceiling_bytes or count + errors >= max_pages:
                    break
                if (page.size_bytes > max_move_bytes - moved_bytes
                        or page.size_bytes > target_ceiling_bytes - used_target):
                    continue
                try:
                    new_handle = self._storage.move(page.handle, page.tier, target)
                except Exception:
                    self._counters["storage_errors"] += 1
                    errors += 1
                    continue
                page.handle = new_handle
                page.tier = target
                # Migration is not a user cache hit: preserve retention age.
                self._counters["migrations"] += 1
                count += 1
                moved_bytes += page.size_bytes
                used_source -= page.size_bytes
                used_target += page.size_bytes
            return {"moved_pages": count, "moved_bytes": moved_bytes,
                    "source_bytes": used_source, "target_bytes": used_target,
                    "remaining_pressure_bytes": max(0, used_source - source_ceiling_bytes),
                    "storage_errors": errors}

    def prefetch_candidates(self, *, target: CacheTier = CacheTier.GPU, limit: int = 16) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            now = self._clock()
            pages = [page for page in self._pages.values() if page.tier != target]
            pages.sort(key=lambda page: self._retention_score(page, now), reverse=True)
            return tuple(page.key for page in pages[:limit])

    def invalidate_namespace(self, namespace: KVNamespace) -> int:
        namespace_fp = namespace.fingerprint()
        with self._lock:
            if any(self._pages[key].pin_count for key in self._namespace_pages.get(namespace_fp, ())):
                raise RuntimeError("KV namespace has active page leases; drain before invalidation")
            removed = 0
            for key in tuple(self._namespace_pages.get(namespace_fp, ())):
                if key in self._pages:
                    removed += self._drop(key, eviction=False)
            self._counters["invalidations"] += int(bool(removed))
            return removed

    def clear(self) -> int:
        with self._lock:
            if any(page.pin_count for page in self._pages.values()):
                raise RuntimeError("KV cache has active page leases; drain before clearing")
            removed = 0
            for key in tuple(self._pages):
                if key in self._pages:
                    removed += self._drop(key, eviction=False)
            self._counters["invalidations"] += int(bool(removed))
            return removed

    def _retention_score(self, page: _Page, now: float) -> float:
        age = max(0.0, now - page.last_access)
        recency = math.exp(-math.log(2.0) * age / self.config.recency_half_life_seconds)
        frequency = self._frequency.get(page.key, 0) + page.hit_count + 1
        return (
            frequency
            * page.recompute_cost
            * page.retention_bias
            * (0.25 + 0.75 * recency)
            * (0.75 + _TIER_WEIGHT[page.tier])
            / max(1.0, math.sqrt(page.size_bytes))
        )

    def _pin_protected_keys(self) -> set[str]:
        """Return pages whose subtree contains at least one pinned page.

        Each pinned page walks toward its root only until it reaches an already
        protected ancestor, so shared ancestry is processed once and long
        prefix chains never consume Python recursion depth.
        """

        protected: set[str] = set()
        for key, page in self._pages.items():
            if not page.pin_count:
                continue
            current = key
            while current in self._pages and current not in protected:
                protected.add(current)
                current = self._pages[current].parent_key
        return protected

    def _subtree_pinned(self, key: str) -> bool:
        return key in self._pin_protected_keys()

    def _candidate(self, trust_domain: str | None) -> _Page | None:
        now = self._clock()
        protected = self._pin_protected_keys()
        candidate: _Page | None = None
        candidate_rank: tuple[float, float, str] | None = None
        for page in self._pages.values():
            if page.key in protected:
                continue
            if trust_domain is not None and page.namespace.trust_domain != trust_domain:
                continue
            rank = (self._retention_score(page, now), page.last_access, page.key)
            if candidate_rank is None or rank < candidate_rank:
                candidate = page
                candidate_rank = rank
        return candidate

    def _enforce_limits(self, trust_domain: str | None) -> None:
        limit = self.config.trust_domain_max_bytes
        if trust_domain is not None and limit is not None:
            while self._trust_bytes.get(trust_domain, 0) > limit:
                victim = self._candidate(trust_domain)
                if victim is None:
                    break
                self._drop(victim.key, eviction=True)
        while self._resident_bytes > self.config.max_bytes or len(self._pages) > self.config.max_entries:
            victim = self._candidate(None)
            if victim is None:
                break
            self._drop(victim.key, eviction=True)

    def _drop(self, key: str, *, eviction: bool) -> int:
        page = self._pages.get(key)
        if page is None or (eviction and self._subtree_pinned(key)):
            return 0

        order: list[str] = []
        stack = [key]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen or current not in self._pages:
                continue
            seen.add(current)
            order.append(current)
            stack.extend(self._children.get(current, ()))

        removed = 0
        for current in reversed(order):
            page = self._pages.pop(current, None)
            if page is None:
                continue
            self._children.pop(current, None)
            siblings = self._children.get(page.parent_key)
            if siblings is not None:
                siblings.discard(current)
                if not siblings:
                    self._children.pop(page.parent_key, None)
            namespace_keys = self._namespace_pages.get(page.namespace_fp)
            if namespace_keys is not None:
                namespace_keys.discard(current)
                if not namespace_keys:
                    self._namespace_pages.pop(page.namespace_fp, None)

            self._frequency.pop(current, None)
            self._resident_bytes -= page.size_bytes
            self._trust_bytes[page.namespace.trust_domain] -= page.size_bytes
            if self._trust_bytes[page.namespace.trust_domain] <= 0:
                self._trust_bytes.pop(page.namespace.trust_domain, None)
            if self._storage is not None:
                try:
                    self._storage.release(page.handle, page.tier)
                except Exception:
                    self._counters["storage_errors"] += 1
            if eviction:
                self._counters["evictions"] += 1
                self._counters["evicted_bytes"] += page.size_bytes
            removed += 1
        return removed

    def audit(self) -> KVIntegrityReport:
        with self._lock:
            orphans: list[str] = []
            mismatches: list[str] = []
            actual_bytes = 0
            trust_bytes: dict[str, int] = defaultdict(int)
            for key, page in self._pages.items():
                actual_bytes += page.size_bytes
                trust_bytes[page.namespace.trust_domain] += page.size_bytes
                root = self._root(page.namespace_fp)
                if page.parent_key != root and page.parent_key not in self._pages:
                    orphans.append(key)
                if key not in self._namespace_pages.get(page.namespace_fp, set()):
                    mismatches.append(key)
                if key not in self._children.get(page.parent_key, set()):
                    mismatches.append(key)
            byte_ok = actual_bytes == self._resident_bytes and dict(trust_bytes) == dict(self._trust_bytes)
            orphan_tuple = tuple(sorted(set(orphans)))
            mismatch_tuple = tuple(sorted(set(mismatches)))
            return KVIntegrityReport(
                valid=not orphan_tuple and not mismatch_tuple and byte_ok,
                resident_pages=len(self._pages),
                resident_bytes=actual_bytes,
                orphan_pages=orphan_tuple,
                index_mismatches=mismatch_tuple,
                byte_accounting_ok=byte_ok,
            )

    def stats(self) -> KVCacheStats:
        with self._lock:
            c = self._counters
            return KVCacheStats(
                lookups=c["lookups"],
                hits=c["hits"],
                full_hits=c["full_hits"],
                token_hits=c["token_hits"],
                token_lookups=c["token_lookups"],
                stores=c["stores"],
                deduplicated_pages=c["deduplicated_pages"],
                evictions=c["evictions"],
                evicted_bytes=c["evicted_bytes"],
                verification_failures=c["verification_failures"],
                migrations=c["migrations"],
                invalidations=c["invalidations"],
                storage_errors=c["storage_errors"],
                resident_pages=len(self._pages),
                resident_bytes=self._resident_bytes,
            )


class KVCacheTransaction:
    """Atomic visibility boundary for speculative/branch decoding."""

    def __init__(self, manager: KVCacheManager, namespace: KVNamespace) -> None:
        self._manager = manager
        self._namespace = namespace
        self._staged: tuple[tuple[int, ...], tuple[KVPageInput, ...], bool] | None = None
        self._closed = False

    def stage(
        self,
        tokens: Sequence[int],
        pages: Sequence[KVPageInput],
        *,
        pin: bool = False,
    ) -> "KVCacheTransaction":
        if self._closed:
            raise RuntimeError("transaction is already closed")
        self._staged = (self._manager._validate_tokens(tokens), tuple(pages), pin)
        return self

    def commit(self) -> tuple[str, ...]:
        if self._closed:
            raise RuntimeError("transaction is already closed")
        if self._staged is None:
            raise RuntimeError("transaction has no staged prefix")
        self._closed = True
        tokens, pages, pin = self._staged
        return self._manager.commit_prefix(tokens, pages, self._namespace, pin=pin)

    def rollback(self) -> None:
        if not self._closed:
            self._staged = None
            self._closed = True

    def __enter__(self) -> "KVCacheTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._closed and self._staged is not None:
            self.commit()
        else:
            self.rollback()
        return False
