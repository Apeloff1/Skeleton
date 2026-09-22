"""tiered_depth — namespaced TieredCache + admit decision cache.

Builds on ``skeleton.kernel.tiered_cache.TieredCache`` with namespaces,
prefix invalidation, stampede-safe fill via Coalescer board, and chaos-
aware caching policy for Pack A API admit depth.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from skeleton.kernel.chaos import ChaosGovernor, Rung
from skeleton.kernel.tiered_cache import TieredCache
from skeleton.kernel.pack_a.coalesce_depth import KeyedFlightBoard, coalesce_get_or_compute

T = TypeVar("T")


@dataclass
class TierStats:
    namespace: str
    l1_entries: int
    l2_entries: int
    hits: int
    misses: int
    fills: int
    invalidations: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "l1_entries": self.l1_entries,
            "l2_entries": self.l2_entries,
            "hits": self.hits,
            "misses": self.misses,
            "fills": self.fills,
            "invalidations": self.invalidations,
        }


class CacheNamespace:
    """One namespaced TieredCache with local counters."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.cache = TieredCache()
        self.fills = 0
        self.invalidations = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        return self.cache.get(self._k(key))

    def put(self, key: str, value: Any) -> None:
        self.cache.put(self._k(key), value)

    def invalidate(self, key: str) -> None:
        self.cache.invalidate(self._k(key))
        with self._lock:
            self.invalidations += 1

    def mark_fill(self) -> None:
        with self._lock:
            self.fills += 1

    def stats(self) -> TierStats:
        raw = self.cache.stats()
        with self._lock:
            fills = self.fills
            inv = self.invalidations
        return TierStats(
            namespace=self.name,
            l1_entries=int(raw.get("l1_entries", 0)),
            l2_entries=int(raw.get("l2_entries", 0)),
            hits=int(raw.get("hits", 0)),
            misses=int(raw.get("misses", 0)),
            fills=fills,
            invalidations=inv,
        )

    def _k(self, key: str) -> str:
        return f"{self.name}:{key}"


class PrefixInvalidator:
    """Best-effort prefix invalidation via tracked key sets per namespace."""

    def __init__(self, ns: CacheNamespace, *, max_tracked: int = 8192) -> None:
        self._ns = ns
        self._max = int(max_tracked)
        self._keys: List[str] = []
        self._lock = threading.Lock()

    def track(self, key: str) -> None:
        with self._lock:
            self._keys.append(key)
            if len(self._keys) > self._max:
                del self._keys[0 : len(self._keys) - self._max]

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            victims = [k for k in self._keys if k.startswith(prefix)]
            self._keys = [k for k in self._keys if not k.startswith(prefix)]
        for k in victims:
            self._ns.invalidate(k)
        return len(victims)


class ChaosCachePolicy:
    """Gate cache fills using ChaosGovernor.should_cache()."""

    def __init__(self, governor: Optional[ChaosGovernor] = None) -> None:
        self.governor = governor if governor is not None else ChaosGovernor()

    def should_cache(self) -> bool:
        return bool(self.governor.should_cache())

    def rung(self) -> Rung:
        return self.governor.rung()


class StampedeSafeCache:
    """get_or_compute through KeyedFlightBoard + CacheNamespace."""

    def __init__(
        self,
        ns: CacheNamespace,
        board: Optional[KeyedFlightBoard] = None,
        policy: Optional[ChaosCachePolicy] = None,
    ) -> None:
        self.ns = ns
        self.board = board if board is not None else KeyedFlightBoard()
        self.policy = policy if policy is not None else ChaosCachePolicy()
        self._tracker = PrefixInvalidator(ns)

    def get_or_compute(self, key: str, compute: Callable[[], T]) -> T:
        hit = self.ns.get(key)
        if hit is not None:
            return hit

        def fill() -> T:
            value = compute()
            if self.policy.should_cache():
                self.ns.put(key, value)
                self.ns.mark_fill()
                self._tracker.track(key)
            return value

        return coalesce_get_or_compute(self.board, f"{self.ns.name}:{key}", fill)

    def invalidate_prefix(self, prefix: str) -> int:
        return self._tracker.invalidate_prefix(prefix)


class NamespacedTieredCache:
    """Registry of CacheNamespace instances."""

    def __init__(self) -> None:
        self._ns: Dict[str, CacheNamespace] = {}
        self._lock = threading.Lock()

    def namespace(self, name: str) -> CacheNamespace:
        with self._lock:
            ns = self._ns.get(name)
            if ns is None:
                ns = CacheNamespace(name)
                self._ns[name] = ns
            return ns

    def stats(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._ns.values())
        return [n.stats().as_dict() for n in items]


class AdmitDecision(Enum):
    ADMITTED = "admitted"
    SHED = "shed"
    EMERGENCY_READ_ONLY = "emergency_read_only"
    OPEN_ROUTE = "open_route"
    SAFE_METHOD = "safe_method"


@dataclass
class AdmitDecisionRecord:
    decision: AdmitDecision
    priority: int
    route_class: str
    when: float
    ttl_s: float

    def expired(self, now: Optional[float] = None) -> bool:
        ts = time.monotonic() if now is None else now
        return (ts - self.when) >= self.ttl_s

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "priority": self.priority,
            "route_class": self.route_class,
            "when": self.when,
            "ttl_s": self.ttl_s,
        }


class AdmitDecisionCache:
    """Short-TTL cache of recent admit outcomes (not a security boundary).

    Used to coalesce repeated identical mutating probes under load. Seal /
    auth still run independently — this only memoizes gate/governor outcomes
    for identical route_class+priority tuples within TTL.
    """

    def __init__(self, *, default_ttl_s: float = 0.05, max_entries: int = 2048) -> None:
        self.default_ttl_s = float(default_ttl_s)
        self.max_entries = int(max_entries)
        self._store: Dict[str, AdmitDecisionRecord] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _key(self, route_class: str, priority: int, path: str) -> str:
        return f"{route_class}|{priority}|{path}"

    def get(
        self, route_class: str, priority: int, path: str
    ) -> Optional[AdmitDecisionRecord]:
        key = self._key(route_class, priority, path)
        with self._lock:
            rec = self._store.get(key)
            if rec is None or rec.expired():
                if rec is not None:
                    self._store.pop(key, None)
                    if key in self._order:
                        self._order.remove(key)
                self.misses += 1
                return None
            self.hits += 1
            return rec

    def put(
        self,
        route_class: str,
        priority: int,
        path: str,
        decision: AdmitDecision,
        *,
        ttl_s: Optional[float] = None,
    ) -> AdmitDecisionRecord:
        key = self._key(route_class, priority, path)
        rec = AdmitDecisionRecord(
            decision=decision,
            priority=int(priority),
            route_class=route_class,
            when=time.monotonic(),
            ttl_s=self.default_ttl_s if ttl_s is None else float(ttl_s),
        )
        with self._lock:
            if key not in self._store:
                self._order.append(key)
            self._store[key] = rec
            while len(self._order) > self.max_entries:
                victim = self._order.pop(0)
                self._store.pop(victim, None)
        return rec

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "default_ttl_s": self.default_ttl_s,
                "max_entries": self.max_entries,
            }


_CACHES = NamespacedTieredCache()
_ADMIT = AdmitDecisionCache()


def default_namespaced_cache() -> NamespacedTieredCache:
    return _CACHES


def default_admit_cache() -> AdmitDecisionCache:
    return _ADMIT


def reset_default_caches_for_tests() -> None:
    global _CACHES, _ADMIT
    _CACHES = NamespacedTieredCache()
    _ADMIT = AdmitDecisionCache()


# Stable namespace catalog for Pack A
PACK_A_CACHE_NAMESPACES = (
    "admit.decision",
    "admit.priority",
    "api.idempotency",
    "forge.plan",
    "gameforge.intake",
    "swarm.policy",
)


__all__ = [
    "AdmitDecision",
    "AdmitDecisionCache",
    "AdmitDecisionRecord",
    "CacheNamespace",
    "ChaosCachePolicy",
    "NamespacedTieredCache",
    "PACK_A_CACHE_NAMESPACES",
    "PrefixInvalidator",
    "StampedeSafeCache",
    "TierStats",
    "default_admit_cache",
    "default_namespaced_cache",
    "reset_default_caches_for_tests",
]
