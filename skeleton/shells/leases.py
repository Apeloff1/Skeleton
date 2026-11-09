"""In-process execution leases for stampede control."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable
import uuid


@dataclass(frozen=True)
class Lease:
    lease_id: str
    key: str
    owner: str
    acquired_at: float
    expires_at: float

    @property
    def ttl_seconds(self) -> float:
        return max(0.0, self.expires_at - self.acquired_at)


class LeaseConflict(RuntimeError):
    pass


class LeaseRegistry:
    """Small TTL lease table; no background thread or hidden renewal."""

    def __init__(self, *, max_leases: int = 1024, clock: Callable[[], float] = time.monotonic) -> None:
        if max_leases <= 0:
            raise ValueError("max_leases must be positive")
        self.max_leases = max_leases
        self._clock = clock
        self._leases: dict[str, Lease] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = self._clock()
        expired = [key for key, lease in self._leases.items() if lease.expires_at <= now]
        for key in expired:
            del self._leases[key]

    def acquire(self, key: str, owner: str, *, ttl_seconds: float = 30.0) -> Lease:
        if not key or not owner:
            raise ValueError("lease key and owner are required")
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        with self._lock:
            self._prune()
            existing = self._leases.get(key)
            if existing is not None:
                raise LeaseConflict(f"lease already held for {key!r}")
            if len(self._leases) >= self.max_leases:
                raise LeaseConflict("lease capacity exhausted")
            now = self._clock()
            lease = Lease(uuid.uuid4().hex, key, owner, now, now + ttl_seconds)
            self._leases[key] = lease
            return lease

    def renew(self, lease: Lease, *, ttl_seconds: float | None = None) -> Lease:
        with self._lock:
            self._prune()
            current = self._leases.get(lease.key)
            if current is None or current.lease_id != lease.lease_id:
                raise LeaseConflict("lease is no longer current")
            ttl = lease.ttl_seconds if ttl_seconds is None else ttl_seconds
            if ttl <= 0:
                raise ValueError("lease ttl must be positive")
            now = self._clock()
            renewed = Lease(lease.lease_id, lease.key, lease.owner, now, now + ttl)
            self._leases[lease.key] = renewed
            return renewed

    def release(self, lease: Lease) -> bool:
        with self._lock:
            current = self._leases.get(lease.key)
            if current is None or current.lease_id != lease.lease_id:
                return False
            del self._leases[lease.key]
            return True

    def held(self, key: str) -> bool:
        with self._lock:
            self._prune()
            return key in self._leases

    def snapshot(self) -> tuple[Lease, ...]:
        with self._lock:
            self._prune()
            return tuple(sorted(self._leases.values(), key=lambda lease: lease.key))
