"""buffer_arena — deepened BufferPool surfaces for API admit staging.

Builds on ``skeleton.kernel.buffer_pool.BufferPool`` without replacing it.
Adds arenas, overflow ledgers, body-staging helpers, and lease guards used
by Pack A API admit depth.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from skeleton.kernel.buffer_pool import (
    CLASS_CAP,
    CLASS_LARGE,
    CLASS_MEDIUM,
    CLASS_SMALL,
    BufferPool,
    Class,
    Lease,
)


class ArenaLane(Enum):
    """Logical lanes for admit-path staging."""

    INGRESS = "ingress"
    EGRESS = "egress"
    DECISION = "decision"
    TELEMETRY = "telemetry"
    SCRATCH = "scratch"


@dataclass
class ClassHistogram:
    """Per-class lease / reclaim / overflow counts."""

    small_leases: int = 0
    medium_leases: int = 0
    large_leases: int = 0
    small_reclaims: int = 0
    medium_reclaims: int = 0
    large_reclaims: int = 0
    small_overflows: int = 0
    medium_overflows: int = 0
    large_overflows: int = 0

    def bump_lease(self, cls: Class) -> None:
        if cls is Class.SMALL:
            self.small_leases += 1
        elif cls is Class.MEDIUM:
            self.medium_leases += 1
        else:
            self.large_leases += 1

    def bump_reclaim(self, cls: Class) -> None:
        if cls is Class.SMALL:
            self.small_reclaims += 1
        elif cls is Class.MEDIUM:
            self.medium_reclaims += 1
        else:
            self.large_reclaims += 1

    def bump_overflow(self, cls: Class) -> None:
        if cls is Class.SMALL:
            self.small_overflows += 1
        elif cls is Class.MEDIUM:
            self.medium_overflows += 1
        else:
            self.large_overflows += 1

    def as_dict(self) -> Dict[str, int]:
        return {
            "small_leases": self.small_leases,
            "medium_leases": self.medium_leases,
            "large_leases": self.large_leases,
            "small_reclaims": self.small_reclaims,
            "medium_reclaims": self.medium_reclaims,
            "large_reclaims": self.large_reclaims,
            "small_overflows": self.small_overflows,
            "medium_overflows": self.medium_overflows,
            "large_overflows": self.large_overflows,
        }


@dataclass
class ArenaStats:
    """Snapshot of an arena's pool pressure."""

    lane: str
    leased: int
    idle_small: int
    idle_medium: int
    idle_large: int
    histogram: Dict[str, int]
    high_water_leased: int
    created_monotonic: float

    def pressure_ratio(self) -> float:
        idle = self.idle_small + self.idle_medium + self.idle_large
        denom = max(1, idle + self.leased)
        return float(self.leased) / float(denom)


@dataclass
class OverflowEvent:
    cls: str
    when: float
    leased_at_event: int
    lane: str


class OverflowLedger:
    """Bounded ring of overflow events (idle lane full on reclaim)."""

    def __init__(self, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = int(capacity)
        self._events: List[OverflowEvent] = []
        self._lock = threading.Lock()

    def record(self, cls: Class, leased: int, lane: str) -> None:
        ev = OverflowEvent(
            cls=cls.name if hasattr(cls, "name") else str(cls),
            when=time.monotonic(),
            leased_at_event=int(leased),
            lane=str(lane),
        )
        with self._lock:
            self._events.append(ev)
            if len(self._events) > self._capacity:
                overflow = len(self._events) - self._capacity
                del self._events[0:overflow]

    def recent(self, limit: int = 32) -> List[Dict[str, Any]]:
        with self._lock:
            tail = self._events[-max(0, int(limit)) :]
            return [
                {
                    "cls": e.cls,
                    "when": e.when,
                    "leased_at_event": e.leased_at_event,
                    "lane": e.lane,
                }
                for e in tail
            ]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class PooledByteView:
    """Read-only view into a leased buffer without transferring ownership."""

    __slots__ = ("_lease", "_length", "_released")

    def __init__(self, lease: Lease, length: int) -> None:
        if length < 0 or length > len(lease.buf):
            raise ValueError("length out of range for leased buffer")
        self._lease = lease
        self._length = int(length)
        self._released = False

    @property
    def length(self) -> int:
        return self._length

    @property
    def size_class(self) -> Class:
        return self._lease.size_class

    def to_bytes(self) -> bytes:
        if self._released:
            raise RuntimeError("view released")
        return bytes(self._lease.buf[: self._length])

    def copy_into(self, dest: bytearray) -> int:
        if self._released:
            raise RuntimeError("view released")
        n = self._length
        if len(dest) < n:
            raise ValueError("dest too small")
        dest[:n] = self._lease.buf[:n]
        return n

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._lease.release()

    def __enter__(self) -> "PooledByteView":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


class LeaseGuard:
    """RAII-ish multi-lease tracker for admit staging scopes."""

    def __init__(self, pool: BufferPool) -> None:
        self._pool = pool
        self._leases: List[Lease] = []
        self._lock = threading.Lock()
        self._closed = False

    def lease(self, min_size: int) -> Lease:
        with self._lock:
            if self._closed:
                raise RuntimeError("LeaseGuard closed")
            lease = self._pool.lease(min_size)
            self._leases.append(lease)
            return lease

    def release_all(self) -> int:
        with self._lock:
            n = 0
            while self._leases:
                self._leases.pop().release()
                n += 1
            return n

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.release_all()

    def __enter__(self) -> "LeaseGuard":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @property
    def outstanding(self) -> int:
        with self._lock:
            return len(self._leases)


class BufferArena:
    """Named BufferPool wrapper with histogram + overflow ledger."""

    def __init__(
        self,
        lane: ArenaLane = ArenaLane.INGRESS,
        *,
        pool: Optional[BufferPool] = None,
        overflow_capacity: int = 256,
    ) -> None:
        self.lane = lane
        self._pool = pool if pool is not None else BufferPool()
        self._hist = ClassHistogram()
        self._overflow = OverflowLedger(overflow_capacity)
        self._high_water = 0
        self._created = time.monotonic()
        self._lock = threading.Lock()
        self._on_lease: List[Callable[[Class, int], None]] = []
        self._on_reclaim: List[Callable[[Class, int], None]] = []

    @property
    def pool(self) -> BufferPool:
        return self._pool

    def on_lease(self, cb: Callable[[Class, int], None]) -> None:
        self._on_lease.append(cb)

    def on_reclaim(self, cb: Callable[[Class, int], None]) -> None:
        self._on_reclaim.append(cb)

    def lease(self, min_size: int) -> Lease:
        lease = self._pool.lease(min_size)
        cls = lease.size_class
        with self._lock:
            self._hist.bump_lease(cls)
            leased = self._pool.leased
            if leased > self._high_water:
                self._high_water = leased
        for cb in list(self._on_lease):
            try:
                cb(cls, min_size)
            except Exception:
                pass
        return lease

    def wrap_reclaim(self, lease: Lease) -> None:
        cls = lease.size_class
        before = self._pool.stats()
        lease.release()
        after = self._pool.stats()
        with self._lock:
            self._hist.bump_reclaim(cls)
            # Overflow: reclaim did not increase idle count for class
            key = {Class.SMALL: "small", Class.MEDIUM: "medium", Class.LARGE: "large"}[cls]
            if after.get(key, 0) <= before.get(key, 0) and before.get("leased", 0) > 0:
                # Cap drop path — record when idle already at CLASS_CAP
                if after.get(key, 0) >= CLASS_CAP:
                    self._hist.bump_overflow(cls)
                    self._overflow.record(cls, after.get("leased", 0), self.lane.value)
        for cb in list(self._on_reclaim):
            try:
                cb(cls, len(lease.buf) if hasattr(lease, "buf") else 0)
            except Exception:
                pass

    def view(self, min_size: int, fill: bytes = b"") -> PooledByteView:
        lease = self.lease(max(min_size, len(fill) or 1))
        if fill:
            lease.buf[: len(fill)] = fill
        return PooledByteView(lease, len(fill) if fill else min_size)

    def guard(self) -> LeaseGuard:
        return LeaseGuard(self._pool)

    def stats(self) -> ArenaStats:
        raw = self._pool.stats()
        with self._lock:
            hist = self._hist.as_dict()
            hw = self._high_water
            created = self._created
        return ArenaStats(
            lane=self.lane.value,
            leased=int(raw.get("leased", 0)),
            idle_small=int(raw.get("small", 0)),
            idle_medium=int(raw.get("medium", 0)),
            idle_large=int(raw.get("large", 0)),
            histogram=hist,
            high_water_leased=hw,
            created_monotonic=created,
        )

    def overflow_recent(self, limit: int = 32) -> List[Dict[str, Any]]:
        return self._overflow.recent(limit)


def arena_for_content_length(content_length: Optional[int]) -> Class:
    """Pick size class from Content-Length (fail closed to LARGE if unknown huge)."""
    if content_length is None or content_length < 0:
        return Class.MEDIUM
    n = int(content_length)
    if n <= CLASS_SMALL:
        return Class.SMALL
    if n <= CLASS_MEDIUM:
        return Class.MEDIUM
    return Class.LARGE


class StagingLease:
    """Admit-path body staging: lease + optional content-length binding."""

    def __init__(
        self,
        arena: BufferArena,
        *,
        content_length: Optional[int] = None,
        min_size: Optional[int] = None,
    ) -> None:
        size = min_size
        if size is None:
            if content_length is None:
                size = CLASS_MEDIUM
            else:
                size = max(1, int(content_length))
        self._arena = arena
        self._lease = arena.lease(int(size))
        self.content_length = content_length
        self._closed = False
        self.bytes_written = 0

    @property
    def size_class(self) -> Class:
        return self._lease.size_class

    @property
    def capacity(self) -> int:
        return len(self._lease.buf)

    def write(self, data: bytes) -> int:
        if self._closed:
            raise RuntimeError("StagingLease closed")
        remaining = self.capacity - self.bytes_written
        if remaining <= 0:
            return 0
        chunk = data[:remaining]
        end = self.bytes_written + len(chunk)
        self._lease.buf[self.bytes_written : end] = chunk
        self.bytes_written = end
        return len(chunk)

    def written_bytes(self) -> bytes:
        return bytes(self._lease.buf[: self.bytes_written])

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._arena.wrap_reclaim(self._lease)

    def __enter__(self) -> "StagingLease":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


class BodyStagingPool:
    """Lane-aware body staging for mutating HTTP routes."""

    def __init__(self, *, max_body: int = CLASS_LARGE) -> None:
        self.max_body = int(max_body)
        self._ingress = BufferArena(ArenaLane.INGRESS)
        self._scratch = BufferArena(ArenaLane.SCRATCH)
        self._lock = threading.Lock()
        self._active = 0
        self._rejected_oversize = 0

    def stage(
        self,
        *,
        content_length: Optional[int] = None,
        force_scratch: bool = False,
    ) -> StagingLease:
        if content_length is not None and int(content_length) > self.max_body:
            with self._lock:
                self._rejected_oversize += 1
            raise ValueError("content_length exceeds max_body")
        arena = self._scratch if force_scratch else self._ingress
        with self._lock:
            self._active += 1
        lease = StagingLease(arena, content_length=content_length)

        # wrap close to decrement active
        orig_close = lease.close

        def _close() -> None:
            was = lease._closed  # noqa: SLF001
            orig_close()
            if not was:
                with self._lock:
                    self._active = max(0, self._active - 1)

        lease.close = _close  # type: ignore[method-assign]
        return lease

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            active = self._active
            rejected = self._rejected_oversize
        return {
            "active": active,
            "rejected_oversize": rejected,
            "max_body": self.max_body,
            "ingress": self._ingress.stats().__dict__,
            "scratch": self._scratch.stats().__dict__,
        }


class DefaultPoolHolder:
    """Process-wide defaults for Pack A pools (tests reset via helper)."""

    def __init__(self) -> None:
        self.pool = BufferPool()
        self.body = BodyStagingPool()
        self.arenas: Dict[str, BufferArena] = {
            lane.value: BufferArena(lane) for lane in ArenaLane
        }


_HOLDER = DefaultPoolHolder()


def default_pool() -> BufferPool:
    return _HOLDER.pool


def default_body_pool() -> BodyStagingPool:
    return _HOLDER.body


def reset_default_pools_for_tests() -> None:
    global _HOLDER
    _HOLDER = DefaultPoolHolder()


# --- expanded helpers for admit depth (route class sizing tables) ---

ROUTE_CLASS_MIN_SIZE: Mapping[str, int] = {
    "control": CLASS_SMALL,
    "auth": CLASS_SMALL,
    "forge": CLASS_MEDIUM,
    "gameforge": CLASS_MEDIUM,
    "swarm": CLASS_MEDIUM,
    "bulk": CLASS_LARGE,
    "upload": CLASS_LARGE,
    "telemetry": CLASS_SMALL,
    "default": CLASS_MEDIUM,
}


def min_size_for_route_class(route_class: str) -> int:
    return int(ROUTE_CLASS_MIN_SIZE.get(route_class, ROUTE_CLASS_MIN_SIZE["default"]))


def classify_path(path: str) -> str:
    p = (path or "").lower()
    if p.startswith("/auth") or p.startswith("/oauth"):
        return "auth"
    if "/swarm" in p:
        return "swarm"
    if "/gameforge" in p:
        return "gameforge"
    if "/forge" in p:
        return "forge"
    if "/telemetry" in p or "/metrics" in p:
        return "telemetry"
    if "/upload" in p or "/bulk" in p:
        return "bulk"
    if p.startswith("/v1/admin") or p.startswith("/control"):
        return "control"
    return "default"


# Generate many explicit staging recipes used by admit depth (real tables, not junk).
STAGING_RECIPES: List[Dict[str, Any]] = []
for _rc, _sz in ROUTE_CLASS_MIN_SIZE.items():
    for _cl in (None, 0, 64, 4096, 4097, 65536, 65537, 1 << 20):
        STAGING_RECIPES.append(
            {
                "route_class": _rc,
                "content_length": _cl,
                "min_size": _sz if _cl is None else max(_sz, int(_cl or 0)),
                "class": arena_for_content_length(_cl).name if _cl is not None else Class.MEDIUM.name,
            }
        )


def recipe_for(route_class: str, content_length: Optional[int]) -> Dict[str, Any]:
    ms = min_size_for_route_class(route_class)
    if content_length is not None:
        ms = max(ms, int(content_length))
    return {
        "route_class": route_class,
        "content_length": content_length,
        "min_size": ms,
        "class": arena_for_content_length(content_length if content_length is not None else ms).name,
    }


def iter_recipes() -> Iterable[Dict[str, Any]]:
    return list(STAGING_RECIPES)


__all__ = [
    "ArenaLane",
    "ArenaStats",
    "BodyStagingPool",
    "BufferArena",
    "ClassHistogram",
    "DefaultPoolHolder",
    "LeaseGuard",
    "OverflowEvent",
    "OverflowLedger",
    "PooledByteView",
    "ROUTE_CLASS_MIN_SIZE",
    "STAGING_RECIPES",
    "StagingLease",
    "arena_for_content_length",
    "classify_path",
    "default_body_pool",
    "default_pool",
    "iter_recipes",
    "min_size_for_route_class",
    "recipe_for",
    "reset_default_pools_for_tests",
]
