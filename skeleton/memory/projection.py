"""Derived projection management for canonical durable memory.

Vector, graph, cache, and legacy memory stores are projections. They may fail,
lag, or be rebuilt without becoming authoritative. This module provides the
one-way adapter from canonical MemoryRecord state into those disposable stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import time
from typing import Any, Iterable, Protocol
from urllib.parse import quote, unquote

from skeleton.contracts.memory_record import MemoryRecord, MemoryState
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.memory.core import CAGStore, Chunk, InMemoryTFIDFStore, MAGStore
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk
from skeleton.memory.vector import VectorStore
from skeleton.vault.data_lifecycle import LifecycleError, LifecycleState
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.persistence.memory_repository import (
    MemoryProjectionEvent,
    MemoryProjectionEventCorruption,
    MongoMemoryRepository,
    SQLiteMemoryRepository,
)


class ProjectionAdmissionError(RuntimeError):
    """Material projection rebuild was denied by resource admission."""


class ProjectionState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class MemoryProjection(Protocol):
    name: str

    def upsert(self, record: MemoryRecord) -> None:
        ...

    def delete(self, memory_id: str) -> None:
        ...


def _projection_deletion_target(projection: MemoryProjection) -> str:
    name = str(getattr(projection, "name", "")).strip()
    if not name:
        raise ValueError("governed projection requires a name")
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return "memory-projection-" + digest[:24]


class _MemoryProjectionLifecycleAdapter:
    """Physical lifecycle adapter bound to one live derived projection."""

    _PREFIX = "memory-projection://"

    def __init__(self, projection: MemoryProjection) -> None:
        if not _is_governed_retrieval_projection(projection):
            raise TypeError("projection is not lifecycle-governed")
        self.projection = projection
        self.projection_name = str(projection.name).strip()
        self.target = _projection_deletion_target(projection)

    @classmethod
    def source_ref(
        cls,
        tenant_id: str,
        projection_name: str,
        memory_id: str,
    ) -> str:
        tenant = str(tenant_id).strip()
        name = str(projection_name).strip()
        memory = str(memory_id).strip()
        if not tenant or not name or not memory:
            raise ValueError("projection lifecycle identity is incomplete")
        return (
            cls._PREFIX
            + quote(tenant, safe="")
            + "/"
            + quote(name, safe="")
            + "/"
            + quote(memory, safe="")
        )

    @classmethod
    def parse_source_ref(cls, source_ref: object) -> tuple[str, str, str]:
        raw = str(source_ref).strip()
        if not raw.startswith(cls._PREFIX):
            raise ValueError("projection lifecycle source_ref is invalid")
        tail = raw[len(cls._PREFIX):]
        tenant_raw, sep1, remainder = tail.partition("/")
        projection_raw, sep2, memory_raw = remainder.partition("/")
        if not sep1 or not sep2 or not tenant_raw or not projection_raw or not memory_raw:
            raise ValueError("projection lifecycle source_ref is invalid")
        tenant = unquote(tenant_raw)
        projection_name = unquote(projection_raw)
        memory_id = unquote(memory_raw)
        if not tenant or not projection_name or not memory_id:
            raise ValueError("projection lifecycle source_ref is invalid")
        return tenant, projection_name, memory_id

    async def delete(self, action: Any) -> None:
        tenant, projection_name, memory_id = self.parse_source_ref(
            action.source_ref
        )
        if tenant != str(action.tenant_id):
            raise ValueError("projection lifecycle tenant mismatch")
        if projection_name != self.projection_name:
            raise ValueError("projection lifecycle owner mismatch")
        expected_record_id, _source_ref, expected_target = (
            _retrieval_projection_identity(
                self.projection,
                tenant_id=tenant,
                memory_id=memory_id,
            )
        )
        if expected_record_id != str(action.record_id):
            raise ValueError("projection lifecycle record identity mismatch")
        if expected_target != str(action.target):
            raise ValueError("projection lifecycle target mismatch")
        self.projection.delete(memory_id)


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
    superseded: bool = False

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


def _projection_material_bytes(records: Iterable[MemoryRecord]) -> int:
    total = 0
    for record in records:
        encoded = json.dumps(
            record.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        total += len(encoded)
    return total


def _admit_projection_rebuild(
    runtime: AdmissionRuntime | None,
    budget: ResourceBudget,
    *,
    operation_id: str | None,
    tenant_id: str,
    material_bytes: int,
):
    if runtime is None:
        return None
    op_id = "" if operation_id is None else str(operation_id).strip()
    if not op_id:
        raise ProjectionAdmissionError(
            "admitted projection rebuild requires operation_id"
        )
    try:
        return runtime.admit(
            AdmissionRequest(
                operation_id=op_id,
                tenant_id=str(tenant_id),
                capability="retrieval-index-rebuild",
                budget=budget,
                estimate=UsageEstimate(storage_bytes=material_bytes),
            ),
            now_wall=time.time(),
        )
    except (AdmissionError, AdmissionRuntimeError) as exc:
        raise ProjectionAdmissionError(
            "projection rebuild denied by resource admission"
        ) from exc


def _complete_projection_rebuild(
    runtime: AdmissionRuntime | None,
    lease,
    *,
    material_bytes: int,
    started: float,
) -> None:
    if runtime is None or lease is None:
        return
    try:
        runtime.complete(
            lease.operation_id,
            UsageEstimate(
                storage_bytes=material_bytes,
                wall_seconds=max(0.0, time.monotonic() - started),
            ),
            now_wall=time.time(),
        )
    except AdmissionRuntimeError as exc:
        raise ProjectionAdmissionError(
            "projection rebuild admission reconciliation failed"
        ) from exc


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


def _fence_projection_event(
    event: MemoryProjectionEvent,
    current: MemoryRecord,
) -> bool:
    """Return True when an event is superseded; fail closed on impossible order.

    A pending historical event may survive a rebuild or a bounded dispatcher
    batch. Applying it after a newer canonical version would regress the
    derived store. Older events are therefore acknowledged without replaying
    their stale payload, while same-version events must exactly match current
    canonical state.
    """
    if event.memory_id != current.memory_id:
        raise ValueError("projection event/current memory identity mismatch")
    if event.tenant_id != current.tenant_id or event.namespace != current.namespace:
        raise ValueError("projection event/current authority scope mismatch")
    if event.memory_version > current.version:
        raise ValueError("projection event is ahead of canonical memory")
    if event.memory_version < current.version:
        return True
    if event.record != current:
        raise ValueError("projection event diverges from canonical current version")
    return False


def _retrieval_projection_identity(
    projection: MemoryProjection,
    record: MemoryRecord | None = None,
    *,
    tenant_id: str | None = None,
    memory_id: str | None = None,
) -> tuple[str, str, str]:
    tenant = (
        record.tenant_id
        if record is not None
        else str(tenant_id or "").strip()
    )
    memory = (
        record.memory_id
        if record is not None
        else str(memory_id or "").strip()
    )
    name = str(projection.name).strip()
    if not tenant or not memory or not name:
        raise ValueError("projection lifecycle identity is incomplete")
    material = (
        tenant
        + "\x1f"
        + name
        + "\x1f"
        + memory
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return (
        "retrieval-" + digest[:40],
        _MemoryProjectionLifecycleAdapter.source_ref(
            tenant,
            name,
            memory,
        ),
        _projection_deletion_target(projection),
    )


def _is_governed_retrieval_projection(
    projection: MemoryProjection,
) -> bool:
    return (
        getattr(projection, "governance_plane", None)
        == "retrieval"
    )


def _ensure_retrieval_record(
    governance: GovernanceRegistry,
    projection: MemoryProjection,
    record: MemoryRecord,
) -> str:
    record_id, source_ref, deletion_target = _retrieval_projection_identity(
        projection,
        record,
    )
    try:
        current = governance.lifecycle.get(record_id)
    except LifecycleError:
        current = None

    if current is not None:
        state = current.get("state")
        if state == LifecycleState.DELETED.value:
            if record.state is MemoryState.ACTIVE:
                raise ValueError(
                    "deleted retrieval projection cannot be revived"
                )
            return record_id
        if state == LifecycleState.DELETE_PENDING.value:
            return record_id

    governance.reconcile_canonical_write(
        "retrieval",
        record_id=record_id,
        tenant_id=record.tenant_id,
        source_ref=source_ref,
        data_class=record.data_class,
        purposes=("retrieval-synthesis",),
        deletion_targets=(deletion_target,),
        created_at=record.created_at.timestamp(),
        retention_until=(
            None
            if record.expires_at is None
            else record.expires_at.timestamp()
        ),
        exportable=False,
    )
    return record_id


def _apply_projection_record(
    projection: MemoryProjection,
    record: MemoryRecord,
    *,
    governance: GovernanceRegistry | None,
) -> tuple[int, int]:
    governed = (
        governance is not None
        and _is_governed_retrieval_projection(projection)
    )

    if record.state is MemoryState.ACTIVE:
        if governed:
            assert governance is not None
            _ensure_retrieval_record(
                governance,
                projection,
                record,
            )
        projection.upsert(record)
        return 1, 0

    retrieval_record_id: str | None = None
    plan = None
    if governed:
        assert governance is not None
        retrieval_record_id = _ensure_retrieval_record(
            governance,
            projection,
            record,
        )
        lifecycle = governance.lifecycle.get(
            retrieval_record_id
        )
        if lifecycle["state"] == LifecycleState.DELETED.value:
            projection.delete(record.memory_id)
            return 0, 1
        plan = governance.request_deletion(
            record.tenant_id,
            record_ids=(retrieval_record_id,),
            reason="canonical-memory-tombstone",
        )

    projection.delete(record.memory_id)

    if (
        governance is not None
        and retrieval_record_id is not None
        and plan is not None
    ):
        deletion_target = _projection_deletion_target(projection)
        retrieval_actions = tuple(
            action
            for action in plan.actions
            if action.record_id == retrieval_record_id
            and action.target == deletion_target
        )
        if len(retrieval_actions) != 1:
            raise RuntimeError(
                "retrieval deletion plan is missing physical target"
            )
        governance.acknowledge_deletion(
            plan.plan_id,
            retrieval_record_id,
            deletion_target,
        )
    return 0, 1


def _dispatch_event(
    event: MemoryProjectionEvent,
    projections: tuple[MemoryProjection, ...],
    *,
    governance: GovernanceRegistry | None = None,
) -> ProjectionEventDispatch:
    results: list[ProjectionResult] = []
    for projection in projections:
        try:
            upserted, deleted = _apply_projection_record(
                projection,
                event.record,
                governance=governance,
            )
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
        self.store.delete(record.memory_id)
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

    governance_plane = "retrieval"

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

    governance_plane = "retrieval"

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

    def __init__(
        self,
        repository: SQLiteMemoryRepository,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        rebuild_budget: ResourceBudget | None = None,
        governance: GovernanceRegistry | None = None,
        lifecycle_adapters: Any | None = None,
    ) -> None:
        if not isinstance(repository, SQLiteMemoryRepository):
            raise TypeError("repository must be SQLiteMemoryRepository")
        if (
            admission_runtime is not None
            and not isinstance(admission_runtime, AdmissionRuntime)
        ):
            raise TypeError("admission_runtime must be AdmissionRuntime")
        if governance is not None and not isinstance(
            governance,
            GovernanceRegistry,
        ):
            raise TypeError("governance must be GovernanceRegistry")
        self.repository = repository
        self.admission_runtime = admission_runtime
        if (
            lifecycle_adapters is not None
            and not callable(
                getattr(lifecycle_adapters, "register_deletion", None)
            )
        ):
            raise TypeError(
                "lifecycle_adapters must expose register_deletion"
            )
        self.rebuild_budget = rebuild_budget or ResourceBudget()
        self.governance = governance
        self.lifecycle_adapters = lifecycle_adapters
        self._projection_lifecycle_bindings: dict[
            str,
            tuple[MemoryProjection, _MemoryProjectionLifecycleAdapter],
        ] = {}

    def _bind_projection_lifecycle_adapters(
        self,
        projections: tuple[MemoryProjection, ...],
    ) -> None:
        registry = self.lifecycle_adapters
        if registry is None:
            return
        for projection in projections:
            if not _is_governed_retrieval_projection(projection):
                continue
            target = _projection_deletion_target(projection)
            current = self._projection_lifecycle_bindings.get(target)
            if current is not None:
                if current[0] is not projection:
                    raise ValueError(
                        "governed projection name is already bound "
                        "to a different physical store"
                    )
                continue
            adapter = _MemoryProjectionLifecycleAdapter(projection)
            registry.register_deletion(target, adapter)
            self._projection_lifecycle_bindings[target] = (
                projection,
                adapter,
            )

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
        self._bind_projection_lifecycle_adapters(projection_list)

        active = tuple(r for r in records if r.state is MemoryState.ACTIVE)
        tombstoned = tuple(r for r in records if r.state is MemoryState.TOMBSTONED)
        results: list[ProjectionResult] = []

        for projection in projection_list:
            upserted = deleted = 0
            try:
                for record in records:
                    added, removed = _apply_projection_record(
                        projection,
                        record,
                        governance=self.governance,
                    )
                    upserted += added
                    deleted += removed
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
        self._bind_projection_lifecycle_adapters(projection_list)
        try:
            events = self.repository.pending_projection_events(limit=limit)
        except MemoryProjectionEventCorruption as exc:
            attempt = ProjectionEventDispatch(
                event_id=exc.event_id,
                memory_id=exc.memory_id,
                memory_version=exc.memory_version,
                action=exc.action,
                published=False,
                results=(
                    ProjectionResult(
                        projection="canonical-fence",
                        state=ProjectionState.DEGRADED,
                        error_code=type(exc.__cause__ or exc).__name__,
                    ),
                ),
            )
            return ProjectionDispatchReport(
                attempted_events=1,
                published_events=0,
                blocked_event_id=exc.event_id,
                remaining_pending_sample=1,
                attempts=(attempt,),
            )
        attempts: list[ProjectionEventDispatch] = []
        published = 0
        blocked_event_id: str | None = None

        for event in events:
            try:
                current = self.repository.get(
                    event.memory_id,
                    tenant_id=event.tenant_id,
                    namespace=event.namespace,
                    include_tombstoned=True,
                )
                superseded = _fence_projection_event(event, current)
            except Exception as exc:
                attempt = ProjectionEventDispatch(
                    event_id=event.event_id,
                    memory_id=event.memory_id,
                    memory_version=event.memory_version,
                    action=event.action,
                    published=False,
                    results=(
                        ProjectionResult(
                            projection="canonical-fence",
                            state=ProjectionState.DEGRADED,
                            error_code=type(exc).__name__,
                        ),
                    ),
                )
                attempts.append(attempt)
                blocked_event_id = event.event_id
                break

            attempt = (
                ProjectionEventDispatch(
                    event_id=event.event_id,
                    memory_id=event.memory_id,
                    memory_version=event.memory_version,
                    action=event.action,
                    published=False,
                    results=(),
                    superseded=True,
                )
                if superseded
                else _dispatch_event(
                    event,
                    projection_list,
                    governance=self.governance,
                )
            )
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
                    superseded=attempt.superseded,
                )
            )
            published += 1

        remaining = len(
            self.repository.pending_projection_event_headers(limit=limit)
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
        admission_operation_id: str | None = None,
    ) -> ProjectionSyncReport:
        projection_list = _projection_batch(projections)
        self._bind_projection_lifecycle_adapters(projection_list)
        records = self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=True,
        )
        material_bytes = _projection_material_bytes(records)
        started = time.monotonic()
        lease = _admit_projection_rebuild(
            self.admission_runtime,
            self.rebuild_budget,
            operation_id=admission_operation_id,
            tenant_id=tenant_id,
            material_bytes=material_bytes,
        )
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

        report = self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projection_list,
        )
        _complete_projection_rebuild(
            self.admission_runtime,
            lease,
            material_bytes=material_bytes,
            started=started,
        )
        return report




class AsyncMemoryProjectionCoordinator:
    """Async canonical -> projection synchronizer for Mongo authority."""

    def __init__(
        self,
        repository: MongoMemoryRepository,
        *,
        admission_runtime: AdmissionRuntime | None = None,
        rebuild_budget: ResourceBudget | None = None,
        governance: GovernanceRegistry | None = None,
        lifecycle_adapters: Any | None = None,
    ) -> None:
        if not isinstance(repository, MongoMemoryRepository):
            raise TypeError("repository must be MongoMemoryRepository")
        if (
            admission_runtime is not None
            and not isinstance(admission_runtime, AdmissionRuntime)
        ):
            raise TypeError("admission_runtime must be AdmissionRuntime")
        if governance is not None and not isinstance(
            governance,
            GovernanceRegistry,
        ):
            raise TypeError("governance must be GovernanceRegistry")
        self.repository = repository
        self.admission_runtime = admission_runtime
        if (
            lifecycle_adapters is not None
            and not callable(
                getattr(lifecycle_adapters, "register_deletion", None)
            )
        ):
            raise TypeError(
                "lifecycle_adapters must expose register_deletion"
            )
        self.rebuild_budget = rebuild_budget or ResourceBudget()
        self.governance = governance
        self.lifecycle_adapters = lifecycle_adapters
        self._projection_lifecycle_bindings: dict[
            str,
            tuple[MemoryProjection, _MemoryProjectionLifecycleAdapter],
        ] = {}

    def _bind_projection_lifecycle_adapters(
        self,
        projections: tuple[MemoryProjection, ...],
    ) -> None:
        registry = self.lifecycle_adapters
        if registry is None:
            return
        for projection in projections:
            if not _is_governed_retrieval_projection(projection):
                continue
            target = _projection_deletion_target(projection)
            current = self._projection_lifecycle_bindings.get(target)
            if current is not None:
                if current[0] is not projection:
                    raise ValueError(
                        "governed projection name is already bound "
                        "to a different physical store"
                    )
                continue
            adapter = _MemoryProjectionLifecycleAdapter(projection)
            registry.register_deletion(target, adapter)
            self._projection_lifecycle_bindings[target] = (
                projection,
                adapter,
            )

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
        self._bind_projection_lifecycle_adapters(projection_list)

        active = tuple(r for r in records if r.state is MemoryState.ACTIVE)
        tombstoned = tuple(r for r in records if r.state is MemoryState.TOMBSTONED)
        results: list[ProjectionResult] = []

        for projection in projection_list:
            upserted = deleted = 0
            try:
                for record in records:
                    added, removed = _apply_projection_record(
                        projection,
                        record,
                        governance=self.governance,
                    )
                    upserted += added
                    deleted += removed
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
        self._bind_projection_lifecycle_adapters(projection_list)
        events = await self.repository.pending_projection_events(limit=limit)
        attempts: list[ProjectionEventDispatch] = []
        published = 0
        blocked_event_id: str | None = None

        for event in events:
            try:
                current = await self.repository.get(
                    event.memory_id,
                    tenant_id=event.tenant_id,
                    namespace=event.namespace,
                    include_tombstoned=True,
                )
                superseded = _fence_projection_event(event, current)
            except Exception as exc:
                attempt = ProjectionEventDispatch(
                    event_id=event.event_id,
                    memory_id=event.memory_id,
                    memory_version=event.memory_version,
                    action=event.action,
                    published=False,
                    results=(
                        ProjectionResult(
                            projection="canonical-fence",
                            state=ProjectionState.DEGRADED,
                            error_code=type(exc).__name__,
                        ),
                    ),
                )
                attempts.append(attempt)
                blocked_event_id = event.event_id
                break

            attempt = (
                ProjectionEventDispatch(
                    event_id=event.event_id,
                    memory_id=event.memory_id,
                    memory_version=event.memory_version,
                    action=event.action,
                    published=False,
                    results=(),
                    superseded=True,
                )
                if superseded
                else _dispatch_event(
                    event,
                    projection_list,
                    governance=self.governance,
                )
            )
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
                    superseded=attempt.superseded,
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
        admission_operation_id: str | None = None,
    ) -> ProjectionSyncReport:
        projection_list = _projection_batch(projections)
        self._bind_projection_lifecycle_adapters(projection_list)
        records = await self.repository.list_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            include_tombstoned=True,
        )
        material_bytes = _projection_material_bytes(records)
        started = time.monotonic()
        lease = _admit_projection_rebuild(
            self.admission_runtime,
            self.rebuild_budget,
            operation_id=admission_operation_id,
            tenant_id=tenant_id,
            material_bytes=material_bytes,
        )
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
        report = await self.sync_subject(
            tenant_id=tenant_id,
            namespace=namespace,
            subject_id=subject_id,
            projections=projection_list,
        )
        _complete_projection_rebuild(
            self.admission_runtime,
            lease,
            material_bytes=material_bytes,
            started=started,
        )
        return report

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
    "ProjectionAdmissionError",
    "MemoryProjectionCoordinator",
    "ProjectionDispatchReport",
    "ProjectionEventDispatch",
    "ProjectionResult",
    "ProjectionState",
    "ProjectionSyncReport",
    "TFIDFStoreProjection",
    "VectorStoreProjection",
]
