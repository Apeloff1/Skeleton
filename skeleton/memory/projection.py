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
from skeleton.memory.core import CAGStore, Chunk, InMemoryTFIDFStore, MAGStore
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk
from skeleton.memory.vector import VectorStore
from skeleton.persistence.memory_repository import (
    MemoryProjectionEvent,
    MongoMemoryRepository,
    SQLiteMemoryRepository,
)


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


@dataclass(frozen=True, slots=True)
class ProjectionEventDispatch:
    event_id: str
    memory_id: str
    memory_version: int
    action: str
    published: bool
    results: tuple[ProjectionResult, ...]

    @property
    def degraded(self) -> bool:
        return any(result.state is ProjectionState.DEGRADED for result in self.results)


@dataclass(frozen=True, slots=True)
class ProjectionDispatchReport:
    attempted_events: int
    published_events: int
    blocked_event_id: str | None
    remaining_pending_sample: int
    attempts: tuple[ProjectionEventDispatch, ...]

    @property
    def degraded(self) -> bool:
        return self.blocked_event_id is not None


def _projection_batch(
    projections: Iterable[MemoryProjection],
    *,
    require_nonempty: bool = False,
) -> tuple[MemoryProjection, ...]:
    resolved = tuple(projections)
    if require_nonempty and not resolved:
        raise ValueError("at least one projection is required")
    names = tuple(str(getattr(item, "name", "")).strip() for item in resolved)
    if any(not name for name in names):
        raise ValueError("every projection requires a name")
    if len(set(names)) != len(names):
        raise ValueError("projection names must be unique")
    return resolved


def _dispatch_event(
    event: MemoryProjectionEvent,
    projections: tuple[MemoryProjection, ...],
) -> ProjectionEventDispatch:
    results: list[ProjectionResult] = []
    for projection in projections:
        try:
            if event.action == "upsert":
                projection.upsert(event.record)
                results.append(
                    ProjectionResult(
                        projection=projection.name,
                        state=ProjectionState.HEALTHY,
                        upserted=1,
                    )
                )
            elif event.action == "delete":
                projection.delete(event.memory_id)
                results.append(
                    ProjectionResult(
                        projection=projection.name,
                        state=ProjectionState.HEALTHY,
                        deleted=1,
                    )
                )
            else:
                raise ValueError(f"unsupported projection action: {event.action}")
        except Exception as exc:
            results.append(
                ProjectionResult(
                    projection=projection.name,
                    state=ProjectionState.DEGRADED,
                    error_code=type(exc).__name__,
                )
            )
            break
    return ProjectionEventDispatch(
        event_id=event.event_id,
        memory_id=event.memory_id,
        memory_version=event.memory_version,
        action=event.action,
        published=False,
        results=tuple(results),
    )


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



def _projection_metadata(record: MemoryRecord) -> dict[str, object]:
    return {
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
    }


def _materialized_content(record: MemoryRecord) -> str:
    if record.content is None:
        raise ValueError("projection requires materialized inline content")
    return record.content


class TFIDFStoreProjection:
    """Derived adapter for the built-in sparse in-process RAG store."""

    def __init__(self, name: str, store: InMemoryTFIDFStore) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(store, InMemoryTFIDFStore):
            raise TypeError("store must be InMemoryTFIDFStore")
        self.name = normalized
        self.store = store

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        self.store.add(
            Chunk(
                text=_materialized_content(record),
                chunk_id=record.memory_id,
                metadata=_projection_metadata(record),
            )
        )

    def delete(self, memory_id: str) -> None:
        self.store.delete(memory_id)


class VectorStoreProjection:
    """Derived adapter for the dense vector store."""

    def __init__(self, name: str, store: VectorStore) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(store, VectorStore):
            raise TypeError("store must be VectorStore")
        self.name = normalized
        self.store = store

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        self.store.delete(record.memory_id)
        self.store.add(
            Chunk(
                text=_materialized_content(record),
                chunk_id=record.memory_id,
                metadata=_projection_metadata(record),
            )
        )

    def delete(self, memory_id: str) -> None:
        self.store.delete(memory_id)


class CAGStoreProjection:
    """Derived adapter for contextual associative memory."""

    def __init__(self, name: str, store: CAGStore) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(store, CAGStore):
            raise TypeError("store must be CAGStore")
        self.name = normalized
        self.store = store

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        self.store.store(
            record.memory_id,
            {
                "text": _materialized_content(record),
                "metadata": _projection_metadata(record),
            },
            context=f"{record.tenant_id}:{record.namespace}:{record.subject_id}",
        )

    def delete(self, memory_id: str) -> None:
        self.store.delete(memory_id)


class MAGStoreProjection:
    """Derived adapter for multi-agent episodic memory."""

    def __init__(self, name: str, store: MAGStore) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(store, MAGStore):
            raise TypeError("store must be MAGStore")
        self.name = normalized
        self.store = store

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        self.store.delete(record.memory_id)
        self.store.record(
            record.memory_id,
            _materialized_content(record),
            tags=[
                f"tenant:{record.tenant_id}",
                f"namespace:{record.namespace}",
                f"subject:{record.subject_id}",
                f"kind:{record.kind.value}",
            ],
        )

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
        projection_list = _projection_batch(projections)

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

    def dispatch_pending(
        self,
        *,
        projections: Iterable[MemoryProjection],
        limit: int = 100,
        now=None,
    ) -> ProjectionDispatchReport:
        """Apply durable projection events in order and ack only complete events.

        The first failed event blocks later events. This preserves canonical
        mutation ordering and makes retry behavior deterministic after crashes.
        """
        projection_list = _projection_batch(
            projections,
            require_nonempty=True,
        )
        events = self.repository.pending_projection_events(limit=limit)
        attempts: list[ProjectionEventDispatch] = []
        published = 0
        blocked_event_id: str | None = None

        for event in events:
            attempt = _dispatch_event(event, projection_list)
            if attempt.degraded:
                attempts.append(attempt)
                blocked_event_id = event.event_id
                break

            self.repository.mark_projection_published(
                event.event_id,
                now=now,
            )
            attempts.append(
                ProjectionEventDispatch(
                    event_id=attempt.event_id,
                    memory_id=attempt.memory_id,
                    memory_version=attempt.memory_version,
                    action=attempt.action,
                    published=True,
                    results=attempt.results,
                )
            )
            published += 1

        remaining = len(
            self.repository.pending_projection_events(limit=limit)
        )
        return ProjectionDispatchReport(
            attempted_events=len(attempts),
            published_events=published,
            blocked_event_id=blocked_event_id,
            remaining_pending_sample=remaining,
            attempts=tuple(attempts),
        )

    def expire_and_sync_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
        now=None,
    ) -> ProjectionSyncReport:
        self.repository.expire_due(
            tenant_id=tenant_id,
            namespace=namespace,
            now=now,
        )
        return self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projections,
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
        projection_list = _projection_batch(projections)
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




class AsyncMemoryProjectionCoordinator:
    """Async canonical -> projection synchronizer for Mongo authority."""

    def __init__(self, repository: MongoMemoryRepository) -> None:
        if not isinstance(repository, MongoMemoryRepository):
            raise TypeError("repository must be MongoMemoryRepository")
        self.repository = repository

    async def export_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        include_tombstoned: bool = True,
    ) -> tuple[dict[str, object], ...]:
        records = await self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=include_tombstoned,
        )
        return tuple(record.as_dict() for record in records)

    async def sync_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
    ) -> ProjectionSyncReport:
        records = await self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=True,
        )
        projection_list = _projection_batch(projections)

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

    async def dispatch_pending(
        self,
        *,
        projections: Iterable[MemoryProjection],
        limit: int = 100,
        now=None,
    ) -> ProjectionDispatchReport:
        """Async durable projection dispatch over Mongo canonical authority."""
        projection_list = _projection_batch(
            projections,
            require_nonempty=True,
        )
        events = await self.repository.pending_projection_events(limit=limit)
        attempts: list[ProjectionEventDispatch] = []
        published = 0
        blocked_event_id: str | None = None

        for event in events:
            attempt = _dispatch_event(event, projection_list)
            if attempt.degraded:
                attempts.append(attempt)
                blocked_event_id = event.event_id
                break

            await self.repository.mark_projection_published(
                event.event_id,
                now=now,
            )
            attempts.append(
                ProjectionEventDispatch(
                    event_id=attempt.event_id,
                    memory_id=attempt.memory_id,
                    memory_version=attempt.memory_version,
                    action=attempt.action,
                    published=True,
                    results=attempt.results,
                )
            )
            published += 1

        remaining = len(
            await self.repository.pending_projection_events(limit=limit)
        )
        return ProjectionDispatchReport(
            attempted_events=len(attempts),
            published_events=published,
            blocked_event_id=blocked_event_id,
            remaining_pending_sample=remaining,
            attempts=tuple(attempts),
        )

    async def rebuild_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
        known_projection_ids: Iterable[str] = (),
    ) -> ProjectionSyncReport:
        projection_list = _projection_batch(projections)
        known_ids = tuple(
            dict.fromkeys(str(item).strip() for item in known_projection_ids)
        )
        if any(not item for item in known_ids):
            raise ValueError("known_projection_ids must be non-empty ids")
        for projection in projection_list:
            try:
                for memory_id in known_ids:
                    projection.delete(memory_id)
            except Exception:
                pass
        return await self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projection_list,
        )

    async def expire_and_sync_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        projections: Iterable[MemoryProjection],
        now=None,
    ) -> ProjectionSyncReport:
        await self.repository.expire_due(
            tenant_id=tenant_id,
            namespace=namespace,
            now=now,
        )
        return await self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projections,
        )


__all__ = [
    "AsyncMemoryProjectionCoordinator",
    "CAGStoreProjection",
    "LegacyMemoryStoreProjection",
    "MAGStoreProjection",
    "MemoryProjection",
    "MemoryProjectionCoordinator",
    "ProjectionDispatchReport",
    "ProjectionEventDispatch",
    "ProjectionResult",
    "ProjectionState",
    "ProjectionSyncReport",
    "TFIDFStoreProjection",
    "VectorStoreProjection",
]
