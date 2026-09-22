"""Backend protocols for durable multi-instance AI shell state."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from skeleton.shells.ai.distributed_state import FencedLease, VersionedValue


@runtime_checkable
class VersionedStateBackend(Protocol):
    def get(self, namespace: str, key: str) -> VersionedValue[object] | None: ...

    def put_if_absent(
        self,
        namespace: str,
        key: str,
        value: object,
    ) -> VersionedValue[object]: ...

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
        value: object,
    ) -> VersionedValue[object]: ...

    def delete(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
    ) -> bool: ...


@runtime_checkable
class RecordListingBackend(VersionedStateBackend, Protocol):
    """Optional backend capability used by bounded maintenance scanners."""

    def records(
        self,
        namespace: str | None = None,
    ) -> tuple[VersionedValue[object], ...]: ...


@runtime_checkable
class FencedLeaseBackend(Protocol):
    def acquire_lease(
        self,
        namespace: str,
        key: str,
        *,
        owner: str,
        ttl_seconds: float,
    ) -> FencedLease: ...

    def renew_lease(
        self,
        lease: FencedLease,
        *,
        ttl_seconds: float,
    ) -> FencedLease: ...

    def release_lease(self, lease: FencedLease) -> bool: ...

    def require_fence(self, lease: FencedLease) -> None: ...


@runtime_checkable
class DistributedAIBackend(VersionedStateBackend, FencedLeaseBackend, Protocol):
    def fenced_compare_and_swap(
        self,
        lease: FencedLease,
        *,
        expected_revision: int,
        value: object,
    ) -> VersionedValue[object]: ...
