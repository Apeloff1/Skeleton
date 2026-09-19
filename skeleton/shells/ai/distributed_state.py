"""Reference compare-and-swap and fencing semantics for distributed AI state.

This in-memory implementation defines expected behavior for durable backends.
Production multi-instance deployments can implement the same interface over a
transactional database or coordination service.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable, Generic, TypeVar

from skeleton.shells.state_conflicts import (
    DistributedStateConflict,
    LeaseConflict,
)


T = TypeVar("T")


@dataclass(frozen=True)
class VersionedValue(Generic[T]):
    namespace: str
    key: str
    revision: int
    value: T

    def to_dict(self) -> dict[str, object]:
        return {
            "namespace": self.namespace,
            "key": self.key,
            "revision": self.revision,
            "value": self.value,
        }


@dataclass(frozen=True)
class FencedLease:
    namespace: str
    key: str
    owner: str
    fencing_token: int
    acquired_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return False

    def active(self, now: float) -> bool:
        return now < self.expires_at

    def to_dict(self) -> dict[str, object]:
        return {
            "namespace": self.namespace,
            "key": self.key,
            "owner": self.owner,
            "fencing_token": self.fencing_token,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }


class InMemoryFencedStore:
    """Reference state store with monotonic per-resource fencing tokens."""

    def __init__(
        self,
        *,
        max_records: int = 100000,
        max_leases: int = 100000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_records <= 0 or max_leases <= 0:
            raise ValueError("distributed state limits must be positive")
        self.max_records = max_records
        self.max_leases = max_leases
        self._clock = clock
        self._records: dict[tuple[str, str], VersionedValue[object]] = {}
        self._leases: dict[tuple[str, str], FencedLease] = {}
        self._tokens: dict[tuple[str, str], int] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _identity(namespace: str, key: str) -> tuple[str, str]:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid distributed namespace")
        if not key or len(key) > 512:
            raise ValueError("invalid distributed key")
        return namespace, key

    def get(self, namespace: str, key: str) -> VersionedValue[object] | None:
        identity = self._identity(namespace, key)
        with self._lock:
            return self._records.get(identity)

    def put_if_absent(
        self,
        namespace: str,
        key: str,
        value: object,
    ) -> VersionedValue[object]:
        identity = self._identity(namespace, key)
        with self._lock:
            existing = self._records.get(identity)
            if existing is not None:
                raise DistributedStateConflict("distributed record already exists")
            if len(self._records) >= self.max_records:
                raise RuntimeError("distributed record capacity exhausted")
            record = VersionedValue(namespace, key, 1, value)
            self._records[identity] = record
            return record

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
        value: object,
    ) -> VersionedValue[object]:
        identity = self._identity(namespace, key)
        with self._lock:
            existing = self._records.get(identity)
            if existing is None:
                if expected_revision != 0:
                    raise DistributedStateConflict("distributed record is missing")
                return self.put_if_absent(namespace, key, value)
            if existing.revision != expected_revision:
                raise DistributedStateConflict("distributed record revision conflict")
            record = VersionedValue(
                namespace,
                key,
                existing.revision + 1,
                value,
            )
            self._records[identity] = record
            return record

    def delete(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
    ) -> bool:
        identity = self._identity(namespace, key)
        with self._lock:
            existing = self._records.get(identity)
            if existing is None:
                return False
            if existing.revision != expected_revision:
                raise DistributedStateConflict("distributed delete revision conflict")
            del self._records[identity]
            return True

    def _current_lease(self, identity: tuple[str, str]) -> FencedLease | None:
        lease = self._leases.get(identity)
        if lease is not None and not lease.active(self._clock()):
            del self._leases[identity]
            lease = None
        return lease

    def acquire_lease(
        self,
        namespace: str,
        key: str,
        *,
        owner: str,
        ttl_seconds: float,
    ) -> FencedLease:
        identity = self._identity(namespace, key)
        if not owner or len(owner) > 256:
            raise ValueError("invalid lease owner")
        if ttl_seconds <= 0:
            raise ValueError("lease TTL must be positive")
        with self._lock:
            current = self._current_lease(identity)
            if current is not None:
                if current.owner == owner:
                    raise LeaseConflict("owner already holds active lease")
                raise LeaseConflict("distributed resource is leased")
            if identity not in self._leases and len(self._leases) >= self.max_leases:
                raise RuntimeError("distributed lease capacity exhausted")
            token = self._tokens.get(identity, 0) + 1
            self._tokens[identity] = token
            now = self._clock()
            lease = FencedLease(
                namespace,
                key,
                owner,
                token,
                now,
                now + ttl_seconds,
            )
            self._leases[identity] = lease
            return lease

    def renew_lease(
        self,
        lease: FencedLease,
        *,
        ttl_seconds: float,
    ) -> FencedLease:
        if ttl_seconds <= 0:
            raise ValueError("lease TTL must be positive")
        identity = self._identity(lease.namespace, lease.key)
        with self._lock:
            current = self._current_lease(identity)
            if current is None:
                raise LeaseConflict("lease expired")
            if current != lease:
                raise LeaseConflict("stale lease cannot be renewed")
            now = self._clock()
            renewed = FencedLease(
                current.namespace,
                current.key,
                current.owner,
                current.fencing_token,
                current.acquired_at,
                now + ttl_seconds,
            )
            self._leases[identity] = renewed
            return renewed

    def release_lease(self, lease: FencedLease) -> bool:
        identity = self._identity(lease.namespace, lease.key)
        with self._lock:
            current = self._current_lease(identity)
            if current is None:
                return False
            if current != lease:
                raise LeaseConflict("stale lease cannot release current owner")
            del self._leases[identity]
            return True

    def require_fence(self, lease: FencedLease) -> None:
        identity = self._identity(lease.namespace, lease.key)
        with self._lock:
            current = self._current_lease(identity)
            if current is None:
                raise LeaseConflict("no active lease")
            if current.owner != lease.owner:
                raise LeaseConflict("lease owner mismatch")
            if current.fencing_token != lease.fencing_token:
                raise LeaseConflict("stale fencing token")
            if current != lease:
                raise LeaseConflict("lease instance is stale")

    def fenced_compare_and_swap(
        self,
        lease: FencedLease,
        *,
        expected_revision: int,
        value: object,
    ) -> VersionedValue[object]:
        self.require_fence(lease)
        return self.compare_and_swap(
            lease.namespace,
            lease.key,
            expected_revision=expected_revision,
            value=value,
        )

    def records(self, namespace: str | None = None) -> tuple[VersionedValue[object], ...]:
        with self._lock:
            items = list(self._records.values())
        if namespace is not None:
            items = [item for item in items if item.namespace == namespace]
        items.sort(key=lambda item: (item.namespace, item.key))
        return tuple(items)

    def leases(self) -> tuple[FencedLease, ...]:
        with self._lock:
            identities = list(self._leases)
            active = []
            for identity in identities:
                lease = self._current_lease(identity)
                if lease is not None:
                    active.append(lease)
        active.sort(key=lambda item: (item.namespace, item.key))
        return tuple(active)
