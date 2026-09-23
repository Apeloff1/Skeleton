"""Derived projection management for canonical durable memory.

Vector, graph, cache, and legacy memory stores are projections. They may fail,
lag, or be rebuilt without becoming authoritative. This module provides the
one-way adapter from canonical MemoryRecord state into those disposable stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol

from skeleton.contracts.memory_record import MemoryRecord, MemoryState
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk
from skeleton.persistence.memory_repository import SQLiteMemoryRepository


class ProjectionState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class MemoryProjection(Protocol):
    name: str

    def upsert(self, record: MemoryRecord) -> None:
        ...

    def delete(self, memory_id: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    projection: str
    state: ProjectionState
    upserted: int = 0
    deleted: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectionSyncReport:
    tenant_id: str
    namespace: str
    subject_id: str
    authoritative_records: int
    active_records: int
    tombstones: int
    results: tuple[ProjectionResult, ...]

    @property
    def degraded(self) -> bool:
        return any(result.state is ProjectionState.DEGRADED for result in self.results)


class LegacyMemoryStoreProjection:
    """Write-only projection adapter for legacy MemoryStore implementations."""

    def __init__(self, name: str, store: MemoryStore) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(store, MemoryStore):
            raise TypeError("store must implement MemoryStore")
        self.name = normalized
        self.store = store

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        content = record.content
        if content is None:
            # A projection may not dereference arbitrary canonical refs by
            # itself. The materializer responsible for content_ref must do so
            # before this adapter is used.
            raise ValueError("projection requires materialized inline content")
        chunk = MemoryChunk(
            id=record.memory_id,
            text=content,
            metadata={
                "canonical_memory_id": record.memory_id,
                "canonical_version": record.version,
                "tenant_id": record.tenant_id,
                "namespace": record.namespace,
                "subject_id": record.subject_id,
                "kind": record.kind.value,
                "payload_digest": record.payload_digest,
                "provenance_refs": list(record.provenance_refs),
                "source_operation_id": record.source_operation_id,
                "data_class": record.data_class,
            },
            source_tier=f"derived:{self.name}",
        )
        self.store.add(chunk)

    def delete(self, memory_id: str) -> None:
        self.store.delete(memory_id)


class MemoryProjectionCoordinator:
    """One-way canonical -> projection synchronizer.

    Projection errors are reported as degraded and never mutate, roll back, or
    reinterpret canonical records.
    """

    def __init__(self, repository: SQLiteMemoryRepository) -> None:
        if not isinstance(repository, SQLiteMemoryRepository):
            raise TypeError("repository must be SQLiteMemoryRepository")
        self.repository = repository

    def export_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        include_tombstoned: bool = True,
    ) -> tuple[dict[str, object], ...]:
        records = self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=include_tombstoned,
        )
        return tuple(record.as_dict() for record in records)

    def sync_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
    ) -> ProjectionSyncReport:
        records = self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=True,
        )
        projection_list = tuple(projections)
        if any(not getattr(item, "name", "") for item in projection_list):
            raise ValueError("every projection requires a name")

        active = tuple(r for r in records if r.state is MemoryState.ACTIVE)
        tombstoned = tuple(r for r in records if r.state is MemoryState.TOMBSTONED)
        results: list[ProjectionResult] = []

        for projection in projection_list:
            upserted = deleted = 0
            try:
                for record in records:
                    if record.state is MemoryState.ACTIVE:
                        projection.upsert(record)
                        upserted += 1
                    else:
                        projection.delete(record.memory_id)
                        deleted += 1
                results.append(
                    ProjectionResult(
                        projection=projection.name,
                        state=ProjectionState.HEALTHY,
                        upserted=upserted,
                        deleted=deleted,
                    )
                )
            except Exception as exc:
                results.append(
                    ProjectionResult(
                        projection=projection.name,
                        state=ProjectionState.DEGRADED,
                        upserted=upserted,
                        deleted=deleted,
                        error_code=type(exc).__name__,
                    )
                )

        return ProjectionSyncReport(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            authoritative_records=len(records),
            active_records=len(active),
            tombstones=len(tombstoned),
            results=tuple(results),
        )

    def rebuild_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
        known_projection_ids: Iterable[str] = (),
    ) -> ProjectionSyncReport:
        projection_list = tuple(projections)
        known_ids = tuple(dict.fromkeys(str(item).strip() for item in known_projection_ids))
        if any(not item for item in known_ids):
            raise ValueError("known_projection_ids must be non-empty ids")

        # Best-effort purge of stale projection rows. A failed purge degrades
        # that projection during the subsequent sync; canonical state remains
        # untouched and can be retried.
        for projection in projection_list:
            try:
                for memory_id in known_ids:
                    projection.delete(memory_id)
            except Exception:
                # sync_subject will surface the projection's current ability to
                # rebuild canonical rows; stale removal can be retried safely.
                pass

        return self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projection_list,
        )


__all__ = [
    "LegacyMemoryStoreProjection",
    "MemoryProjection",
    "MemoryProjectionCoordinator",
    "ProjectionResult",
    "ProjectionState",
    "ProjectionSyncReport",
]
