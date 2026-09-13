"""Bounded infrastructure contracts distilled from GameForge Rust.

Source: Apeloff1/gameforge-rs, crates/gf-services/src/lib.rs
Revision: 8f0a107e5cac31fbfe39fee07daad415fd453aca
Disposition: selective promotion; Python contract layer, no Rust/vendor coupling.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from time import monotonic


@dataclass
class _Entry:
    value: object
    inserted: float
    hits: int = 0


class TieredCache:
    """Bounded L1/L2 cache with TTL and hot-entry promotion."""

    def __init__(self, l1_cap: int = 512, l2_cap: int = 4096,
                 l1_ttl: float = 60.0, l2_ttl: float = 300.0) -> None:
        if min(l1_cap, l2_cap) <= 0 or min(l1_ttl, l2_ttl) <= 0:
            raise ValueError("cache bounds must be positive")
        self.l1_cap, self.l2_cap = l1_cap, l2_cap
        self.l1_ttl, self.l2_ttl = l1_ttl, l2_ttl
        self._l1: OrderedDict[str, _Entry] = OrderedDict()
        self._l2: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = Lock()
        self.hits = self.misses = 0

    def get(self, key: str, now: float | None = None) -> object | None:
        now = monotonic() if now is None else now
        with self._lock:
            e = self._l1.get(key)
            if e and now - e.inserted < self.l1_ttl:
                self._l1.move_to_end(key)
                self.hits += 1
                return e.value
            if e:
                self._l1.pop(key, None)
            e = self._l2.get(key)
            if e and now - e.inserted < self.l2_ttl:
                e.hits += 1
                value = e.value
                if e.hits >= 2:
                    self._put_l1(key, value, now)
                self.hits += 1
                return value
            if e:
                self._l2.pop(key, None)
            self.misses += 1
            return None

    def put(self, key: str, value: object, now: float | None = None) -> None:
        now = monotonic() if now is None else now
        with self._lock:
            self._put_l2(key, value, now)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._l1.pop(key, None)
            self._l2.pop(key, None)

    def _put_l1(self, key: str, value: object, now: float) -> None:
        self._l1.pop(key, None)
        self._l1[key] = _Entry(value, now)
        while len(self._l1) > self.l1_cap:
            self._l1.popitem(last=False)

    def _put_l2(self, key: str, value: object, now: float) -> None:
        self._l2.pop(key, None)
        self._l2[key] = _Entry(value, now)
        while len(self._l2) > self.l2_cap:
            self._l2.popitem(last=False)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"l1_entries": len(self._l1), "l2_entries": len(self._l2),
                    "hits": self.hits, "misses": self.misses}


class Verdict(str, Enum):
    ADMITTED = "admitted"
    SHED = "shed"


class AdaptiveGate:
    """Bounded token admission with explicit shedding under saturation."""

    def __init__(self, capacity: int, refill_per_sec: int) -> None:
        if capacity <= 0 or refill_per_sec < 0:
            raise ValueError("invalid gate bounds")
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = capacity
        self.admitted = self.shed = 0
        self._last = monotonic()
        self._lock = Lock()

    def admit(self, priority: int = 1, now: float | None = None) -> Verdict:
        now = monotonic() if now is None else now
        with self._lock:
            elapsed = max(0.0, now - self._last)
            self.tokens = min(self.capacity,
                              self.tokens + int(elapsed * self.refill_per_sec))
            if elapsed * self.refill_per_sec >= 1:
                self._last = now
            if self.tokens == 0 and priority > 0:
                self.shed += 1
                return Verdict.SHED
            self.tokens = max(0, self.tokens - 1)
            self.admitted += 1
            return Verdict.ADMITTED

    def stats(self) -> dict[str, int]:
        return {"tokens_available": self.tokens, "capacity": self.capacity,
                "admitted": self.admitted, "shed": self.shed}


class ChaosState(str, Enum):
    NORMAL = "normal"
    REDUCED_CACHING = "reduced_caching"
    SHED_BACKGROUND = "shed_background"
    STALE_READS = "stale_reads"
    EMERGENCY_READ_ONLY = "emergency_read_only"


class ChaosGovernor:
    """Monotonic degradation state machine for failure cascades."""

    _ORDER = (ChaosState.NORMAL, ChaosState.REDUCED_CACHING,
              ChaosState.SHED_BACKGROUND, ChaosState.STALE_READS,
              ChaosState.EMERGENCY_READ_ONLY)

    def __init__(self) -> None:
        self.state = ChaosState.NORMAL

    def degrade(self) -> ChaosState:
        i = self._ORDER.index(self.state)
        self.state = self._ORDER[min(i + 1, len(self._ORDER) - 1)]
        return self.state

    def recover(self) -> ChaosState:
        i = self._ORDER.index(self.state)
        self.state = self._ORDER[max(0, i - 1)]
        return self.state

    @property
    def read_only(self) -> bool:
        return self.state is ChaosState.EMERGENCY_READ_ONLY

    @property
    def allow_background(self) -> bool:
        return self._ORDER.index(self.state) < self._ORDER.index(ChaosState.SHED_BACKGROUND)
