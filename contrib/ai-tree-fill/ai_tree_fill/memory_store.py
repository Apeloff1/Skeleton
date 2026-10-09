"""Versioned store and fenced leases. The protocol ellipses stay the contract."""

from __future__ import annotations

import time
from dataclasses import dataclass


class StoreConflict(RuntimeError):
    pass


class FenceError(RuntimeError):
    pass


@dataclass
class VersionedValue:
    namespace: str
    key: str
    revision: int
    value: object


@dataclass
class FencedLease:
    namespace: str
    key: str
    owner: str
    fence: int
    expires_at: float


class MemoryDistributedBackend:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], VersionedValue] = {}
        self._leases: dict[tuple[str, str], FencedLease] = {}
        self._fence = 0

    def get(self, namespace: str, key: str) -> VersionedValue | None:
        return self._rows.get((namespace, key))

    def put_if_absent(self, namespace: str, key: str, value: object) -> VersionedValue:
        slot = (namespace, key)
        if slot in self._rows:
            raise StoreConflict(f"present {namespace}/{key}")
        row = VersionedValue(namespace, key, 1, value)
        self._rows[slot] = row
        return row

    def compare_and_swap(self, namespace: str, key: str, *, expected_revision: int, value: object) -> VersionedValue:
        current = self.get(namespace, key)
        if current is None or current.revision != expected_revision:
            raise StoreConflict("revision mismatch")
        row = VersionedValue(namespace, key, current.revision + 1, value)
        self._rows[(namespace, key)] = row
        return row

    def delete(self, namespace: str, key: str, *, expected_revision: int) -> bool:
        current = self.get(namespace, key)
        if current is None or current.revision != expected_revision:
            return False
        del self._rows[(namespace, key)]
        return True

    def records(self, namespace: str | None = None) -> tuple[VersionedValue, ...]:
        rows = self._rows.values()
        if namespace is not None:
            rows = [row for row in rows if row.namespace == namespace]
        return tuple(rows)

    def acquire_lease(self, namespace: str, key: str, *, owner: str, ttl_seconds: float) -> FencedLease:
        slot = (namespace, key)
        now = time.time()
        current = self._leases.get(slot)
        if current and current.expires_at > now and current.owner != owner:
            raise FenceError("lease held")
        self._fence += 1
        lease = FencedLease(namespace, key, owner, self._fence, now + ttl_seconds)
        self._leases[slot] = lease
        return lease

    def renew_lease(self, lease: FencedLease, *, ttl_seconds: float) -> FencedLease:
        self.require_fence(lease)
        renewed = FencedLease(lease.namespace, lease.key, lease.owner, lease.fence, time.time() + ttl_seconds)
        self._leases[(lease.namespace, lease.key)] = renewed
        return renewed

    def release_lease(self, lease: FencedLease) -> bool:
        self.require_fence(lease)
        del self._leases[(lease.namespace, lease.key)]
        return True

    def require_fence(self, lease: FencedLease) -> None:
        current = self._leases.get((lease.namespace, lease.key))
        if current is None or current.fence != lease.fence or current.expires_at < time.time():
            raise FenceError("stale fence")

    def fenced_compare_and_swap(self, lease: FencedLease, *, expected_revision: int, value: object) -> VersionedValue:
        self.require_fence(lease)
        return self.compare_and_swap(lease.namespace, lease.key, expected_revision=expected_revision, value=value)
