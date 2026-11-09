"""Executable data-lifecycle adapters for governed state.

The lifecycle registry owns policy/state transitions; this module performs the
physical deletion/export work.  It deliberately preflights adapters before any
side effect so an unsupported target cannot create an avoidable partial delete.

A deletion receipt is committed only after its physical adapter returns
successfully.  If the process dies after the physical delete but before the
receipt, retry is expected to be idempotent: deleting an already absent record
is success and the registry can then acknowledge the outstanding target.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import inspect
from typing import Any, Mapping, Protocol, runtime_checkable

from skeleton.observability.correlation import correlation_scope, get_correlation_id
from skeleton.persistence.memory_repository import (
    MemoryNotFound,
    MongoMemoryRepository,
    SQLiteMemoryRepository,
)
from skeleton.vault.governance_audit import GovernanceAuditTimeline
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
)


class LifecycleAdapterError(RuntimeError):
    """Base physical lifecycle-adapter failure."""


class LifecycleAdapterMissing(LifecycleAdapterError):
    """No physical adapter is registered for a required target."""


class LifecycleExecutionError(LifecycleAdapterError):
    """A physical adapter failed while executing a lifecycle action."""


def _required_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LifecycleAdapterError(f"{field} is required")
    normalized = value.strip().lower()
    if len(normalized) > 128:
        raise LifecycleAdapterError(f"{field} is too long")
    return normalized


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@runtime_checkable
class DeletionAdapter(Protocol):
    async def delete(self, action: DeletionAction) -> None:
        """Delete one governed record/projection idempotently."""


@runtime_checkable
class ExportAdapter(Protocol):
    async def export(self, record: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return one governed canonical record or None if already absent."""


class LifecycleAdapterRegistry:
    """Explicit mapping from lifecycle targets/owners to physical adapters."""

    def __init__(self) -> None:
        self._deletion: dict[str, DeletionAdapter] = {}
        self._export: dict[str, ExportAdapter] = {}

    def register_deletion(self, target: str, adapter: DeletionAdapter) -> None:
        key = _required_name(target, "deletion target")
        if key in self._deletion and self._deletion[key] is not adapter:
            raise LifecycleAdapterError(f"deletion adapter already registered: {key}")
        self._deletion[key] = adapter

    def register_export(self, owner_plane: str, adapter: ExportAdapter) -> None:
        key = _required_name(owner_plane, "owner plane")
        if key in self._export and self._export[key] is not adapter:
            raise LifecycleAdapterError(f"export adapter already registered: {key}")
        self._export[key] = adapter

    def deletion(self, target: str) -> DeletionAdapter:
        key = _required_name(target, "deletion target")
        try:
            return self._deletion[key]
        except KeyError as exc:
            raise LifecycleAdapterMissing(
                f"missing deletion adapter for target: {key}"
            ) from exc

    def exporter(self, owner_plane: str) -> ExportAdapter:
        key = _required_name(owner_plane, "owner plane")
        try:
            return self._export[key]
        except KeyError as exc:
            raise LifecycleAdapterMissing(
                f"missing export adapter for owner plane: {key}"
            ) from exc

    def missing_deletion_targets(self, plan: DeletionPlan) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    _required_name(action.target, "deletion target")
                    for action in plan.actions
                    if _required_name(action.target, "deletion target") not in self._deletion
                }
            )
        )

    def missing_export_owners(
        self,
        records: tuple[Mapping[str, Any], ...],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    _required_name(row.get("owner_plane"), "owner plane")
                    for row in records
                    if _required_name(row.get("owner_plane"), "owner plane") not in self._export
                }
            )
        )

    def preflight_plan(self, plan: DeletionPlan) -> None:
        missing = self.missing_deletion_targets(plan)
        if missing:
            raise LifecycleAdapterMissing(
                "missing deletion adapters: " + ", ".join(missing)
            )


@dataclass(frozen=True, slots=True)
class DeletionExecutionResult:
    plan_id: str
    receipts: tuple[DeletionReceipt, ...]


@dataclass(frozen=True, slots=True)
class GovernedExport:
    tenant_id: str
    records: tuple[dict[str, Any], ...]


class MemoryDeletionAdapter:
    """Adapter for MemoryContract-like stores exposing delete(item_id)."""

    def __init__(self, store: Any) -> None:
        delete = getattr(store, "delete", None)
        if not callable(delete):
            raise TypeError("memory store must expose delete(item_id)")
        self.store = store

    async def delete(self, action: DeletionAction) -> None:
        await _await_if_needed(self.store.delete(action.record_id))


class SQLiteMemoryLifecycleAdapter:
    """Tenant-scoped lifecycle adapter for canonical SQLite memory authority."""

    _PREFIX = "memory://"

    def __init__(self, repository: SQLiteMemoryRepository) -> None:
        if not isinstance(repository, SQLiteMemoryRepository):
            raise TypeError("repository must be SQLiteMemoryRepository")
        self.repository = repository

    @classmethod
    def source_ref(cls, namespace: str, memory_id: str) -> str:
        normalized_namespace = str(namespace).strip()
        normalized_id = str(memory_id).strip()
        if not normalized_namespace or not normalized_id:
            raise LifecycleAdapterError("memory source reference fields are required")
        if "/" in normalized_namespace:
            raise LifecycleAdapterError("memory namespace cannot contain '/'")
        return cls._PREFIX + normalized_namespace + "/" + normalized_id

    @classmethod
    def _parse_source_ref(cls, source_ref: object) -> tuple[str, str]:
        raw = str(source_ref).strip()
        if not raw.startswith(cls._PREFIX):
            raise LifecycleAdapterError("memory source reference is invalid")
        tail = raw[len(cls._PREFIX) :]
        namespace, separator, memory_id = tail.partition("/")
        if (
            not separator
            or not namespace
            or not memory_id
            or "/" in memory_id
        ):
            raise LifecycleAdapterError("memory source reference is invalid")
        return namespace, memory_id

    async def delete(self, action: DeletionAction) -> None:
        namespace, memory_id = self._parse_source_ref(action.source_ref)
        if memory_id != action.record_id:
            raise LifecycleAdapterError("memory lifecycle identity mismatch")
        try:
            current = self.repository.get(
                memory_id,
                tenant_id=action.tenant_id,
                namespace=namespace,
                include_tombstoned=True,
            )
        except MemoryNotFound:
            return
        if not current.active:
            return
        self.repository.tombstone(
            memory_id,
            tenant_id=action.tenant_id,
            namespace=namespace,
            expected_version=current.version,
        )

    async def export(
        self,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        namespace, memory_id = self._parse_source_ref(record.get("source_ref"))
        if memory_id != str(record.get("record_id")):
            raise LifecycleAdapterError("memory lifecycle identity mismatch")
        try:
            current = self.repository.get(
                memory_id,
                tenant_id=str(record["tenant_id"]),
                namespace=namespace,
                include_tombstoned=False,
            )
        except MemoryNotFound:
            return None
        return current.as_dict()


class MongoMemoryLifecycleAdapter:
    """Tenant-scoped lifecycle adapter for canonical Mongo memory authority."""

    _PREFIX = SQLiteMemoryLifecycleAdapter._PREFIX

    def __init__(self, repository: MongoMemoryRepository) -> None:
        if not isinstance(repository, MongoMemoryRepository):
            raise TypeError("repository must be MongoMemoryRepository")
        self.repository = repository

    @classmethod
    def source_ref(cls, namespace: str, memory_id: str) -> str:
        return SQLiteMemoryLifecycleAdapter.source_ref(
            namespace,
            memory_id,
        )

    @classmethod
    def _parse_source_ref(cls, source_ref: object) -> tuple[str, str]:
        return SQLiteMemoryLifecycleAdapter._parse_source_ref(source_ref)

    async def delete(self, action: DeletionAction) -> None:
        namespace, memory_id = self._parse_source_ref(action.source_ref)
        if memory_id != action.record_id:
            raise LifecycleAdapterError("memory lifecycle identity mismatch")
        try:
            current = await self.repository.get(
                memory_id,
                tenant_id=action.tenant_id,
                namespace=namespace,
                include_tombstoned=True,
            )
        except MemoryNotFound:
            return
        if not current.active:
            return
        await self.repository.tombstone(
            memory_id,
            tenant_id=action.tenant_id,
            namespace=namespace,
            expected_version=current.version,
        )

    async def export(
        self,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        namespace, memory_id = self._parse_source_ref(
            record.get("source_ref")
        )
        if memory_id != str(record.get("record_id")):
            raise LifecycleAdapterError("memory lifecycle identity mismatch")
        try:
            current = await self.repository.get(
                memory_id,
                tenant_id=str(record["tenant_id"]),
                namespace=namespace,
                include_tombstoned=False,
            )
        except MemoryNotFound:
            return None
        return current.as_dict()


class GovernedArtifactLifecycleAdapter:
    """Physical delete/export adapter for canonical governed artifacts."""

    def __init__(self, artifacts: Any) -> None:
        from skeleton.artifact_plane.governance import GovernedArtifactStore

        if not isinstance(artifacts, GovernedArtifactStore):
            raise TypeError("artifacts must be GovernedArtifactStore")
        self.artifacts = artifacts

    def _identity(
        self,
        record_id: object,
        tenant_id: object,
        source_ref: object,
    ) -> tuple[str, str]:
        tenant, artifact_id = self.artifacts.parse_source_ref(
            source_ref
        )
        if tenant != str(tenant_id):
            raise LifecycleAdapterError(
                "artifact lifecycle tenant mismatch"
            )
        expected = self.artifacts.lifecycle_record_id(
            tenant,
            artifact_id,
        )
        if expected != str(record_id):
            raise LifecycleAdapterError(
                "artifact lifecycle identity mismatch"
            )
        return tenant, artifact_id

    async def delete(self, action: DeletionAction) -> None:
        tenant, artifact_id = self._identity(
            action.record_id,
            action.tenant_id,
            action.source_ref,
        )
        await _await_if_needed(
            self.artifacts.remove(tenant, artifact_id)
        )

    async def export(
        self,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        tenant, artifact_id = self._identity(
            record.get("record_id"),
            record.get("tenant_id"),
            record.get("source_ref"),
        )
        return self.artifacts.export_record(
            tenant,
            artifact_id,
        )


class GovernedRetrievalLifecycleAdapter:
    """Physical delete/export adapter for canonical governed retrieval."""

    def __init__(self, retrieval: Any) -> None:
        from skeleton.retrieval.governance import GovernedRetrievalIndex

        if not isinstance(retrieval, GovernedRetrievalIndex):
            raise TypeError(
                "retrieval must be GovernedRetrievalIndex"
            )
        self.retrieval = retrieval

    def _identity(
        self,
        record_id: object,
        tenant_id: object,
        source_ref: object,
    ) -> tuple[str, str]:
        tenant, doc_id = self.retrieval.parse_source_ref(source_ref)
        if tenant != str(tenant_id):
            raise LifecycleAdapterError(
                "retrieval lifecycle tenant mismatch"
            )
        expected = self.retrieval.lifecycle_record_id(tenant, doc_id)
        if expected != str(record_id):
            raise LifecycleAdapterError(
                "retrieval lifecycle identity mismatch"
            )
        return tenant, doc_id

    async def delete(self, action: DeletionAction) -> None:
        tenant, doc_id = self._identity(
            action.record_id,
            action.tenant_id,
            action.source_ref,
        )
        await _await_if_needed(
            self.retrieval.remove(tenant, doc_id)
        )

    async def export(
        self,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        tenant, doc_id = self._identity(
            record.get("record_id"),
            record.get("tenant_id"),
            record.get("source_ref"),
        )
        return self.retrieval.export_record(tenant, doc_id)


class RetrievalIndexDeletionAdapter:
    """Adapter for the in-process retrieval index's idempotent remove()."""

    def __init__(self, index: Any) -> None:
        remove = getattr(index, "remove", None)
        if not callable(remove):
            raise TypeError("retrieval index must expose remove(doc_id)")
        self.index = index

    async def delete(self, action: DeletionAction) -> None:
        # False means the projection is already absent, which is successful
        # idempotent deletion for lifecycle reconciliation.
        await _await_if_needed(self.index.remove(action.record_id))


class MongoCollectionLifecycleAdapter:
    """Duck-typed async Mongo collection adapter.

    The collection must expose delete_one() and find_one().  No Motor/PyMongo
    import is required here, keeping the governance core dependency-neutral.
    Tenant binding is always part of the physical query.
    """

    def __init__(
        self,
        collection: Any,
        *,
        id_field: str = "record_id",
        tenant_field: str = "tenant_id",
    ) -> None:
        if not callable(getattr(collection, "delete_one", None)):
            raise TypeError("Mongo collection must expose delete_one")
        if not callable(getattr(collection, "find_one", None)):
            raise TypeError("Mongo collection must expose find_one")
        self.collection = collection
        self.id_field = _required_name(id_field, "id field")
        self.tenant_field = _required_name(tenant_field, "tenant field")

    def _query(self, record_id: str, tenant_id: str) -> dict[str, str]:
        return {
            self.id_field: str(record_id),
            self.tenant_field: str(tenant_id),
        }

    async def delete(self, action: DeletionAction) -> None:
        await _await_if_needed(
            self.collection.delete_one(
                self._query(action.record_id, action.tenant_id)
            )
        )

    async def export(
        self,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        raw = await _await_if_needed(
            self.collection.find_one(
                self._query(
                    str(record["record_id"]),
                    str(record["tenant_id"]),
                )
            )
        )
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise LifecycleExecutionError("Mongo export returned non-mapping payload")
        payload = dict(raw)
        # Database-native identity is transport metadata, not exported content.
        payload.pop("_id", None)
        return payload


class LifecycleExecutor:
    """Execute governed deletion, retention and export operations."""

    def __init__(
        self,
        lifecycle: DataLifecycleRegistry,
        adapters: LifecycleAdapterRegistry,
        *,
        timeline: GovernanceAuditTimeline | None = None,
    ) -> None:
        self.lifecycle = lifecycle
        self.adapters = adapters
        self.timeline = timeline

    def _correlation_context(self):
        active = get_correlation_id()
        if self.timeline is None or active:
            return nullcontext(active or None)
        return correlation_scope()

    async def execute_deletion_plan(
        self,
        plan: DeletionPlan,
        *,
        now: float | None = None,
    ) -> DeletionExecutionResult:
        with self._correlation_context() as correlation_id:
            if self.timeline is not None:
                self.timeline.record_plan(plan, correlation_id=correlation_id)

            missing = self.adapters.missing_deletion_targets(plan)
            if missing:
                if self.timeline is not None:
                    self.timeline.record_preflight_denied(
                        plan,
                        missing,
                        correlation_id=correlation_id,
                    )
                raise LifecycleAdapterMissing(
                    "missing deletion adapters: " + ", ".join(missing)
                )

            receipts: list[DeletionReceipt] = []
            for action in plan.actions:
                adapter = self.adapters.deletion(action.target)
                try:
                    await adapter.delete(action)
                except Exception as exc:
                    if self.timeline is not None:
                        self.timeline.record_failure(
                            action,
                            exc,
                            correlation_id=correlation_id,
                        )
                    if isinstance(exc, LifecycleAdapterError):
                        raise
                    raise LifecycleExecutionError(
                        f"deletion adapter failed for {action.target}:{action.record_id}"
                    ) from exc

                receipt = self.lifecycle.acknowledge_deletion(
                    plan.plan_id,
                    action.record_id,
                    action.target,
                    now=now,
                )
                receipts.append(receipt)
                if self.timeline is not None:
                    self.timeline.record_receipt(
                        action,
                        receipt,
                        correlation_id=correlation_id,
                    )

            return DeletionExecutionResult(
                plan_id=plan.plan_id,
                receipts=tuple(receipts),
            )

    async def execute_retention_expiry(
        self,
        *,
        now: float | None = None,
    ) -> tuple[DeletionExecutionResult, ...]:
        plans = self.lifecycle.plan_retention_expiry(now=now)
        # Preflight every plan before the first physical side effect.
        with self._correlation_context() as correlation_id:
            for plan in plans:
                missing = self.adapters.missing_deletion_targets(plan)
                if missing:
                    if self.timeline is not None:
                        self.timeline.record_plan(
                            plan,
                            correlation_id=correlation_id,
                        )
                        self.timeline.record_preflight_denied(
                            plan,
                            missing,
                            correlation_id=correlation_id,
                        )
                    raise LifecycleAdapterMissing(
                        "missing deletion adapters: " + ", ".join(missing)
                    )

            results = []
            for plan in plans:
                results.append(await self.execute_deletion_plan(plan, now=now))
            return tuple(results)

    async def export_tenant(self, tenant_id: str) -> GovernedExport:
        inventory = self.lifecycle.export_inventory(tenant_id)
        rows = tuple(inventory["records"])

        with self._correlation_context() as correlation_id:
            missing = self.adapters.missing_export_owners(rows)
            if missing:
                if self.timeline is not None:
                    self.timeline.record_export_denied(
                        str(inventory["tenant_id"]),
                        missing,
                        correlation_id=correlation_id,
                    )
                raise LifecycleAdapterMissing(
                    "missing export adapters: " + ", ".join(missing)
                )

            exported: list[dict[str, Any]] = []
            for row in rows:
                adapter = self.adapters.exporter(str(row["owner_plane"]))
                try:
                    payload = await adapter.export(row)
                except Exception as exc:
                    if self.timeline is not None:
                        self.timeline.record_export_failure(
                            str(inventory["tenant_id"]),
                            str(row["owner_plane"]),
                            exc,
                            correlation_id=correlation_id,
                        )
                    if isinstance(exc, LifecycleAdapterError):
                        raise
                    raise LifecycleExecutionError(
                        f"export adapter failed for {row['owner_plane']}:{row['record_id']}"
                    ) from exc
                exported.append(
                    {
                        "governance": dict(row),
                        "payload": None if payload is None else dict(payload),
                    }
                )

            result = GovernedExport(
                tenant_id=str(inventory["tenant_id"]),
                records=tuple(exported),
            )
            if self.timeline is not None:
                self.timeline.record_export(
                    result.tenant_id,
                    list(result.records),
                    correlation_id=correlation_id,
                )
            return result


__all__ = [
    "DeletionAdapter",
    "DeletionExecutionResult",
    "ExportAdapter",
    "GovernedArtifactLifecycleAdapter",
    "GovernedExport",
    "GovernedRetrievalLifecycleAdapter",
    "LifecycleAdapterError",
    "LifecycleAdapterMissing",
    "LifecycleAdapterRegistry",
    "LifecycleExecutionError",
    "LifecycleExecutor",
    "MemoryDeletionAdapter",
    "MongoCollectionLifecycleAdapter",
    "MongoMemoryLifecycleAdapter",
    "RetrievalIndexDeletionAdapter",
    "SQLiteMemoryLifecycleAdapter",
]
