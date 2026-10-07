"""TieredCache with a durable L3: read-through and write-behind.

Composition, not modification: ``skeleton.kernel.tiered_cache.TieredCache``
keeps its L1/L2 behavior untouched. This wrapper adds:

* read-through: an L1/L2 miss consults pending write-behind entries, then the
  durable tier, and back-fills L2 on a durable hit;
* write-behind: ``put`` updates L1/L2 synchronously and enqueues the durable
  write; ``put(..., durable_sync=True)`` writes through instead;
* coherent invalidation: ``invalidate`` drops L1/L2 and enqueues a durable
  tombstone, so a later read-through cannot resurrect the old value;
* single-flight loaders: concurrent ``get_or_load`` misses for one key share a
  single loader call.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from skeleton.kernel.tiered_cache import TieredCache
from skeleton.persistence.pack_h.durable_tier import _MISSING, DurableTier, WriteBehindQueue


class _Flight:
    __slots__ = ("event", "value", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.value: Any = None
        self.error: Optional[BaseException] = None


class DurableTieredCache:
    def __init__(
        self,
        tier: DurableTier,
        *,
        cache: Optional[TieredCache] = None,
        write_behind: Optional[WriteBehindQueue] = None,
        default_ttl_s: Optional[float] = None,
    ) -> None:
        self.tier = tier
        self.cache = cache if cache is not None else TieredCache()
        self.queue = write_behind if write_behind is not None else WriteBehindQueue(tier)
        if self.queue.tier is not tier:
            raise ValueError("write_behind must target the same durable tier")
        self.default_ttl_s = default_ttl_s
        self._flights: Dict[str, _Flight] = {}
        self._lock = threading.Lock()
        self.read_through_hits = 0
        self.read_through_misses = 0
        self.pending_hits = 0
        self.loader_calls = 0

    def get(self, key: str) -> Optional[Any]:
        value = self.cache.get(key)
        if value is not None:
            return value
        pending = self.queue.pending(key)
        if pending is not _MISSING:
            with self._lock:
                self.pending_hits += 1
            if pending is not None:
                self.cache.put(key, pending)
            return pending
        entry = self.tier.get_entry(key)
        with self._lock:
            if entry is None:
                self.read_through_misses += 1
                return None
            self.read_through_hits += 1
        self.cache.put(key, entry.value)
        return entry.value

    def put(self, key: str, value: Any, *, ttl_s: Optional[float] = None, durable_sync: bool = False) -> None:
        if value is None:
            raise ValueError("None is not cacheable; use invalidate()")
        ttl = self.default_ttl_s if ttl_s is None else ttl_s
        self.cache.put(key, value)
        if durable_sync:
            # Write-through must not be overtaken by an older queued write.
            self.queue.flush()
            self.tier.put(key, value, ttl_s=ttl)
        else:
            self.queue.put(key, value, ttl)

    def invalidate(self, key: str, *, durable_sync: bool = False) -> None:
        self.cache.invalidate(key)
        if durable_sync:
            self.queue.flush()
            self.tier.delete(key)
        else:
            self.queue.delete(key)

    def evict_local(self, key: str) -> None:
        """Drop only L1/L2 (e.g. on a peer's invalidation signal)."""
        self.cache.invalidate(key)

    def get_or_load(self, key: str, loader: Callable[[], Any], *, ttl_s: Optional[float] = None) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        with self._lock:
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = _Flight()
                self._flights[key] = flight
        assert flight is not None
        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value
        try:
            with self._lock:
                self.loader_calls += 1
            loaded = loader()
            if loaded is not None:
                self.put(key, loaded, ttl_s=ttl_s)
            flight.value = loaded
            return loaded
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with self._lock:
                self._flights.pop(key, None)

    def flush(self) -> int:
        return self.queue.flush()

    def close(self) -> None:
        self.queue.close(flush=True)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            local = {
                "read_through_hits": self.read_through_hits,
                "read_through_misses": self.read_through_misses,
                "pending_hits": self.pending_hits,
                "loader_calls": self.loader_calls,
            }
        return {
            "cache": self.cache.stats(),
            "write_behind": self.queue.stats(),
            "durable": self.tier.stats(),
            **local,
        }
