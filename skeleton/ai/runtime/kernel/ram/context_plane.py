"""Adaptive RAM-backed hot context for large AI projects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import threading
import time
from typing import Mapping
import zlib

from skeleton.kernel.ram.topology import MemoryTopology, SystemMemoryProbe

_GIB = 1024**3


class MemoryPressure(str, Enum):
    NORMAL = "normal"
    SOFT = "soft"
    HARD = "hard"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ContextMemoryPolicy:
    host_fraction: float = 0.55
    silicon_fraction: float = 0.65
    board_fraction: float = 0.72
    hbm_fraction: float = 0.78
    cxl_fraction: float = 0.70
    min_os_reserve_bytes: int = _GIB
    os_reserve_fraction: float = 0.10
    max_capacity_bytes: int = 2 * 1024 * _GIB
    max_entry_bytes: int = 256 * 1024**2
    compression_threshold_bytes: int = 4096
    soft_available_ratio: float = 0.25
    hard_available_ratio: float = 0.15
    critical_available_ratio: float = 0.08
    refresh_interval_seconds: float = 2.0

    def __post_init__(self) -> None:
        for value in (
            self.host_fraction, self.silicon_fraction, self.board_fraction,
            self.hbm_fraction, self.cxl_fraction,
        ):
            if not 0 < value <= 0.95:
                raise ValueError("RAM retention fractions must be in (0, .95]")
        if not 0 <= self.os_reserve_fraction < 0.9:
            raise ValueError("invalid OS reserve fraction")
        if not (
            0 < self.critical_available_ratio
            < self.hard_available_ratio
            < self.soft_available_ratio < 1
        ):
            raise ValueError("invalid pressure thresholds")


@dataclass(frozen=True, slots=True)
class ContextMemoryEntry:
    namespace: str
    logical_key: str
    digest: str
    raw_size_bytes: int
    stored_size_bytes: int
    compressed: bool
    priority: int
    pinned: bool


@dataclass(slots=True)
class _Stored:
    namespace: str
    key: str
    digest: str
    payload: bytes
    raw_size: int
    compressed: bool
    priority: int
    pinned: bool
    last_access: int

    @property
    def size(self) -> int:
        return len(self.payload)

    def snapshot(self) -> ContextMemoryEntry:
        return ContextMemoryEntry(
            self.namespace, self.key, self.digest, self.raw_size, self.size,
            self.compressed, self.priority, self.pinned,
        )


class ContextMemoryPlane:
    """Content-addressed RAM reservoir with pressure-aware eviction."""

    def __init__(
        self,
        *,
        topology: MemoryTopology | None = None,
        probe: SystemMemoryProbe | None = None,
        policy: ContextMemoryPolicy | None = None,
    ) -> None:
        if topology is not None and probe is not None:
            raise ValueError("pass topology or probe, not both")
        self._probe = None if topology is not None else (probe or SystemMemoryProbe())
        self.topology = topology or self._probe.probe()
        self.policy = policy or ContextMemoryPolicy()
        self._entries: dict[tuple[str, str], _Stored] = {}
        self._used = self._hits = self._misses = self._evictions = 0
        self._lock = threading.RLock()
        self._capacity = self._budget(
            self.topology.available_bytes, self.topology.total_bytes
        )
        self._pressure = self._pressure_for(
            self.topology.available_bytes, self.topology.total_bytes
        )
        self._refreshed = time.monotonic_ns()

    @property
    def backend(self) -> str:
        if self.topology.has_high_bandwidth_memory:
            return "hbm-system-memory"
        if self.topology.has_board_memory:
            return "board-or-package-memory"
        if any(d.technology.family == "CXL" for d in self.topology.recognized_devices):
            return "cxl-system-memory"
        return "host-ram"

    @property
    def capacity_bytes(self) -> int:
        return self._capacity

    @property
    def used_bytes(self) -> int:
        return self._used

    @property
    def pressure(self) -> MemoryPressure:
        return self._pressure

    def _fraction(self) -> float:
        if self.topology.has_high_bandwidth_memory:
            return self.policy.hbm_fraction
        if self.topology.has_board_memory:
            return self.policy.board_fraction
        if any(d.technology.family == "CXL" for d in self.topology.recognized_devices):
            return self.policy.cxl_fraction
        if self.topology.has_memory_silicon:
            return self.policy.silicon_fraction
        return self.policy.host_fraction

    def _budget(self, available: int, total: int) -> int:
        reserve = max(
            self.policy.min_os_reserve_bytes,
            int(total * self.policy.os_reserve_fraction),
        )
        return min(
            self.policy.max_capacity_bytes,
            max(0, int(max(0, available - reserve) * self._fraction())),
        )

    def _pressure_for(self, available: int, total: int) -> MemoryPressure:
        if total <= 0:
            return MemoryPressure.NORMAL
        ratio = max(0.0, min(1.0, available / total))
        if ratio <= self.policy.critical_available_ratio:
            return MemoryPressure.CRITICAL
        if ratio <= self.policy.hard_available_ratio:
            return MemoryPressure.HARD
        if ratio <= self.policy.soft_available_ratio:
            return MemoryPressure.SOFT
        return MemoryPressure.NORMAL

    def _evict(self, target: int, *, include_pinned: bool) -> None:
        candidates = sorted(
            (
                (key, value) for key, value in self._entries.items()
                if include_pinned or not value.pinned
            ),
            key=lambda item: (
                item[1].priority, item[1].last_access, -item[1].size, item[0]
            ),
        )
        for key, value in candidates:
            if self._used <= target:
                break
            if self._entries.pop(key, None) is not None:
                self._used -= value.size
                self._evictions += 1

    def refresh_pressure(
        self,
        *,
        available_bytes: int | None = None,
        total_bytes: int | None = None,
    ) -> MemoryPressure:
        if available_bytes is None or total_bytes is None:
            if self._probe is None:
                total, available = (
                    self.topology.total_bytes, self.topology.available_bytes
                )
            else:
                total, available = self._probe.capacity_snapshot()
        else:
            total, available = int(total_bytes), int(available_bytes)
        pressure = self._pressure_for(available, total)
        capacity = self._budget(available, total)
        if pressure is MemoryPressure.SOFT:
            capacity = min(capacity, int(self._capacity * 0.8))
        elif pressure is MemoryPressure.HARD:
            capacity = min(capacity, int(self._capacity * 0.5))
        elif pressure is MemoryPressure.CRITICAL:
            capacity = min(capacity, int(self._capacity * 0.2))
        with self._lock:
            self._pressure, self._capacity = pressure, max(0, capacity)
            self._refreshed = time.monotonic_ns()
            self._evict(
                self._capacity,
                include_pinned=pressure is MemoryPressure.CRITICAL,
            )
        return pressure

    def _refresh_if_due(self) -> None:
        if self._probe is None:
            return
        interval = int(self.policy.refresh_interval_seconds * 1_000_000_000)
        if time.monotonic_ns() - self._refreshed >= interval:
            self.refresh_pressure()

    @staticmethod
    def _identity(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("RAM context identity must be non-empty text")
        return value.strip()

    def put(
        self,
        namespace: str,
        logical_key: str,
        payload: str | bytes,
        *,
        priority: int = 0,
        pinned: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> ContextMemoryEntry:
        del metadata  # reserved for callers; payload owns authoritative metadata
        self._refresh_if_due()
        ns, key = self._identity(namespace), self._identity(logical_key)
        raw = payload.encode() if isinstance(payload, str) else bytes(payload)
        if len(raw) > self.policy.max_entry_bytes:
            raise ValueError("RAM context entry exceeds hard bound")
        encoded, compressed = raw, False
        if len(raw) >= self.policy.compression_threshold_bytes:
            packed = zlib.compress(raw, 3)
            if len(packed) < len(raw) * 0.9:
                encoded, compressed = packed, True
        now = time.monotonic_ns()
        entry = _Stored(
            ns, key, hashlib.sha256(raw).hexdigest(), encoded, len(raw),
            compressed, int(priority), bool(pinned), now,
        )
        storage_key = (ns, key)
        with self._lock:
            prior = self._entries.pop(storage_key, None)
            if prior:
                self._used -= prior.size
            if entry.size > self._capacity:
                if prior:
                    self._entries[storage_key] = prior
                    self._used += prior.size
                raise MemoryError("entry exceeds live RAM context budget")
            self._evict(self._capacity - entry.size, include_pinned=False)
            if self._used + entry.size > self._capacity:
                if prior:
                    self._entries[storage_key] = prior
                    self._used += prior.size
                raise MemoryError("RAM context budget is pinned/exhausted")
            self._entries[storage_key] = entry
            self._used += entry.size
        return entry.snapshot()

    @staticmethod
    def _decode(entry: _Stored) -> bytes:
        raw = zlib.decompress(entry.payload) if entry.compressed else entry.payload
        if len(raw) != entry.raw_size or hashlib.sha256(raw).hexdigest() != entry.digest:
            raise RuntimeError("RAM context integrity check failed")
        return raw

    def get(self, namespace: str, logical_key: str) -> bytes | None:
        storage_key = (self._identity(namespace), self._identity(logical_key))
        with self._lock:
            entry = self._entries.get(storage_key)
            if entry is None:
                self._misses += 1
                return None
            try:
                raw = self._decode(entry)
            except RuntimeError:
                self._entries.pop(storage_key, None)
                self._used -= entry.size
                self._misses += 1
                return None
            entry.last_access = time.monotonic_ns()
            self._hits += 1
            return raw

    def scan(
        self, namespace: str, *, limit: int = 512
    ) -> tuple[tuple[ContextMemoryEntry, bytes], ...]:
        self._refresh_if_due()
        ns = self._identity(namespace)
        if not 1 <= limit <= 4096:
            raise ValueError("RAM context scan limit outside hard bounds")
        with self._lock:
            values = sorted(
                (v for (entry_ns, _), v in self._entries.items() if entry_ns == ns),
                key=lambda v: (-v.priority, -v.last_access, v.key),
            )[:limit]
            output = []
            for entry in values:
                try:
                    raw = self._decode(entry)
                except RuntimeError:
                    self._entries.pop((entry.namespace, entry.key), None)
                    self._used -= entry.size
                    continue
                entry.last_access = time.monotonic_ns()
                self._hits += 1
                output.append((entry.snapshot(), raw))
            return tuple(output)

    def delete(self, namespace: str, logical_key: str) -> bool:
        with self._lock:
            entry = self._entries.pop(
                (self._identity(namespace), self._identity(logical_key)), None
            )
            if entry is None:
                return False
            self._used -= entry.size
            return True

    def stats(self) -> dict[str, object]:
        return {
            "kind": "adaptive-context-memory",
            "backend": self.backend,
            "capacity_bytes": self._capacity,
            "used_bytes": self._used,
            "entry_count": len(self._entries),
            "pressure": self._pressure.value,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "technologies": list(self.topology.technologies),
            "board_memory": self.topology.has_board_memory,
            "high_bandwidth_memory": self.topology.has_high_bandwidth_memory,
            "os_addressable_only": True,
            "preallocated_bytes": 0,
        }


_DEFAULT: ContextMemoryPlane | None = None
_DEFAULT_LOCK = threading.Lock()


def get_default_context_memory_plane() -> ContextMemoryPlane:
    global _DEFAULT
    if _DEFAULT is None:
        with _DEFAULT_LOCK:
            if _DEFAULT is None:
                _DEFAULT = ContextMemoryPlane()
    return _DEFAULT


__all__ = [
    "ContextMemoryEntry", "ContextMemoryPlane", "ContextMemoryPolicy",
    "MemoryPressure", "get_default_context_memory_plane",
]
