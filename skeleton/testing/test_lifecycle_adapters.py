from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.frontier.memory import InMemoryStore
from skeleton.persistence.memory_repository import (
    MemoryNotFound,
    SQLiteMemoryRepository,
)
from skeleton.retrieval.governance import GovernedRetrievalIndex
from skeleton.retrieval.index import InvertedIndex
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    DeletionAction,
    GovernedDataRecord,
    LifecycleState,
)
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.vault.lifecycle_adapters import (
    LifecycleAdapterMissing,
    LifecycleAdapterRegistry,
    LifecycleExecutionError,
    GovernedRetrievalLifecycleAdapter,
    LifecycleExecutor,
    MemoryDeletionAdapter,
    MongoCollectionLifecycleAdapter,
    RetrievalIndexDeletionAdapter,
    SQLiteMemoryLifecycleAdapter,
)


def _record(
    record_id: str,
    *,
    owner_plane: str,
    targets: tuple[str, ...],
    tenant: str = "tenant-a",
    retention_until: float | None = None,
) -> GovernedDataRecord:
    return GovernedDataRecord(
        record_id=record_id,
        tenant_id=tenant,
        owner_plane=owner_plane,
        source_ref=f"{owner_plane}://{record_id}",
        data_class="internal",
        purposes=("model-inference",),
        deletion_targets=targets,
        created_at=10.0,
        retention_until=retention_until,
    )


@pytest.mark.asyncio
async def test_memory_deletion_adapter_executes_and_acknowledges() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "m1", "content": "remember me", "metadata": {}})
    lifecycle.register(_record("m1", owner_plane="memory", targets=("memory",)))

    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))
    executor = LifecycleExecutor(lifecycle, adapters)

    plan = lifecycle.request_deletion("tenant-a", record_ids=("m1",), now=20.0)
    result = await executor.execute_deletion_plan(plan, now=21.0)

    assert len(result.receipts) == 1
    assert result.receipts[0].state is LifecycleState.DELETED
    assert await memory.search("", limit=10) == []
    assert lifecycle.get("m1")["state"] == "deleted"


@pytest.mark.asyncio
async def test_retrieval_projection_delete_is_idempotent_when_already_absent() -> None:
    lifecycle = DataLifecycleRegistry()
    index = InvertedIndex()
    index.add("r1", "alpha beta gamma")
    lifecycle.register(_record("r1", owner_plane="retrieval", targets=("retrieval",)))

    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("retrieval", RetrievalIndexDeletionAdapter(index))
    executor = LifecycleExecutor(lifecycle, adapters)

    plan = lifecycle.request_deletion("tenant-a", record_ids=("r1",), now=20.0)
    assert index.remove("r1") is True

    result = await executor.execute_deletion_plan(plan, now=21.0)

    assert len(result.receipts) == 1
    assert result.receipts[0].state is LifecycleState.DELETED
    assert index.size() == 0


@pytest.mark.asyncio
async def test_preflight_missing_adapter_prevents_partial_delete() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "mixed", "content": "keep until preflight passes", "metadata": {}})
    lifecycle.register(
        _record(
            "mixed",
            owner_plane="memory",
            targets=("memory", "artifact"),
        )
    )

    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))
    executor = LifecycleExecutor(lifecycle, adapters)
    plan = lifecycle.request_deletion("tenant-a", record_ids=("mixed",), now=20.0)

    with pytest.raises(LifecycleAdapterMissing, match="artifact"):
        await executor.execute_deletion_plan(plan, now=21.0)

    assert len(await memory.search("", limit=10)) == 1
    assert lifecycle.get("mixed")["state"] == "delete_pending"
    assert lifecycle.receipts() == ()


class _DeleteThenFailOnce:
    def __init__(self, memory: InMemoryStore) -> None:
        self.memory = memory
        self.calls = 0

    async def delete(self, action) -> None:
        self.calls += 1
        await self.memory.delete(action.record_id)
        if self.calls == 1:
            raise RuntimeError("crash after physical delete")


@pytest.mark.asyncio
async def test_retry_after_delete_before_ack_reconciles_idempotently() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "m1", "content": "ambiguous", "metadata": {}})
    lifecycle.register(_record("m1", owner_plane="memory", targets=("memory",)))

    adapter = _DeleteThenFailOnce(memory)
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", adapter)
    executor = LifecycleExecutor(lifecycle, adapters)
    plan = lifecycle.request_deletion("tenant-a", record_ids=("m1",), now=20.0)

    with pytest.raises(LifecycleExecutionError, match="memory:m1"):
        await executor.execute_deletion_plan(plan, now=21.0)

    assert await memory.search("", limit=10) == []
    assert lifecycle.get("m1")["state"] == "delete_pending"
    assert lifecycle.receipts() == ()

    retry = lifecycle.request_deletion("tenant-a", record_ids=("m1",), now=22.0)
    result = await executor.execute_deletion_plan(retry, now=23.0)

    assert adapter.calls == 2
    assert result.receipts[-1].state is LifecycleState.DELETED
    assert lifecycle.get("m1")["state"] == "deleted"


@pytest.mark.asyncio
async def test_retention_execution_preflights_then_deletes() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "expired", "content": "old", "metadata": {}})
    lifecycle.register(
        _record(
            "expired",
            owner_plane="memory",
            targets=("memory",),
            retention_until=15.0,
        )
    )

    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))
    executor = LifecycleExecutor(lifecycle, adapters)

    results = await executor.execute_retention_expiry(now=20.0)

    assert len(results) == 1
    assert results[0].receipts[-1].state is LifecycleState.DELETED
    assert await memory.search("", limit=10) == []


@dataclass
class _DeleteResult:
    deleted_count: int


class _FakeAsyncCollection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.queries: list[tuple[str, dict]] = []

    async def delete_one(self, query: dict) -> _DeleteResult:
        self.queries.append(("delete", dict(query)))
        before = len(self.rows)
        self.rows = [
            row
            for row in self.rows
            if not all(row.get(key) == value for key, value in query.items())
        ]
        return _DeleteResult(before - len(self.rows))

    async def find_one(self, query: dict):
        self.queries.append(("find", dict(query)))
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None


@pytest.mark.asyncio
async def test_mongo_adapter_export_and_delete_are_tenant_scoped() -> None:
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(_record("doc-1", owner_plane="memory", targets=("memory",)))
    collection = _FakeAsyncCollection(
        [
            {"_id": "native", "record_id": "doc-1", "tenant_id": "tenant-a", "value": 7},
            {"_id": "other", "record_id": "doc-1", "tenant_id": "tenant-b", "value": 9},
        ]
    )
    mongo = MongoCollectionLifecycleAdapter(collection)
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", mongo)
    adapters.register_export("memory", mongo)
    executor = LifecycleExecutor(lifecycle, adapters)

    exported = await executor.export_tenant("tenant-a")
    assert exported.tenant_id == "tenant-a"
    assert exported.records[0]["payload"] == {
        "record_id": "doc-1",
        "tenant_id": "tenant-a",
        "value": 7,
    }

    plan = lifecycle.request_deletion("tenant-a", record_ids=("doc-1",), now=20.0)
    await executor.execute_deletion_plan(plan, now=21.0)

    assert collection.rows == [
        {"_id": "other", "record_id": "doc-1", "tenant_id": "tenant-b", "value": 9}
    ]
    assert ("delete", {"record_id": "doc-1", "tenant_id": "tenant-a"}) in collection.queries


@pytest.mark.asyncio
async def test_export_preflight_fails_before_partial_reads() -> None:
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(_record("m1", owner_plane="memory", targets=("memory",)))
    lifecycle.register(_record("a1", owner_plane="artifact", targets=("artifact",)))

    collection = _FakeAsyncCollection(
        [{"record_id": "m1", "tenant_id": "tenant-a", "value": "memory"}]
    )
    adapters = LifecycleAdapterRegistry()
    adapters.register_export("memory", MongoCollectionLifecycleAdapter(collection))
    executor = LifecycleExecutor(lifecycle, adapters)

    with pytest.raises(LifecycleAdapterMissing, match="artifact"):
        await executor.export_tenant("tenant-a")

    assert collection.queries == []



def _memory_proposal(
    *,
    tenant_id: str = "tenant-a",
    namespace: str = "assistant",
    content: str = "remember",
) -> MemoryWriteProposal:
    now = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
    return MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id=tenant_id,
        namespace=namespace,
        subject_id="subject-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key=str(uuid4()),
        proposed_at=now,
        content=content,
        provenance_refs=("conversation:fixture",),
        source_operation_id=str(uuid4()),
        data_class="confidential",
    )


@pytest.mark.asyncio
async def test_sqlite_memory_lifecycle_export_and_delete_are_tenant_scoped(
    tmp_path,
) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    record = repository.commit(_memory_proposal())
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(
        GovernedDataRecord(
            record_id=record.memory_id,
            tenant_id=record.tenant_id,
            owner_plane="memory",
            source_ref=SQLiteMemoryLifecycleAdapter.source_ref(
                record.namespace,
                record.memory_id,
            ),
            data_class=record.data_class,
            purposes=("model-inference",),
            deletion_targets=("memory",),
            created_at=record.created_at.timestamp(),
        )
    )
    adapter = SQLiteMemoryLifecycleAdapter(repository)
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", adapter)
    adapters.register_export("memory", adapter)
    executor = LifecycleExecutor(lifecycle, adapters)

    exported = await executor.export_tenant("tenant-a")
    assert len(exported.records) == 1
    assert exported.records[0]["payload"]["memory_id"] == record.memory_id
    assert exported.records[0]["payload"]["content"] == "remember"

    plan = lifecycle.request_deletion(
        "tenant-a",
        record_ids=(record.memory_id,),
        now=20.0,
    )
    result = await executor.execute_deletion_plan(plan, now=21.0)
    assert result.receipts[-1].state is LifecycleState.DELETED

    with pytest.raises(MemoryNotFound):
        repository.get(
            record.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    tombstone = repository.get(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        include_tombstoned=True,
    )
    assert tombstone.active is False
    pending = repository.pending_projection_events()
    assert pending[-1].action == "delete"


@pytest.mark.asyncio
async def test_sqlite_memory_lifecycle_delete_is_idempotent_after_tombstone(
    tmp_path,
) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    record = repository.commit(_memory_proposal())
    adapter = SQLiteMemoryLifecycleAdapter(repository)
    action = DeletionAction(
        record_id=record.memory_id,
        tenant_id=record.tenant_id,
        target="memory",
        source_ref=SQLiteMemoryLifecycleAdapter.source_ref(
            record.namespace,
            record.memory_id,
        ),
        reason="tenant-request",
    )

    await adapter.delete(action)
    first = repository.get(
        record.memory_id,
        tenant_id=record.tenant_id,
        namespace=record.namespace,
        include_tombstoned=True,
    )
    await adapter.delete(action)
    second = repository.get(
        record.memory_id,
        tenant_id=record.tenant_id,
        namespace=record.namespace,
        include_tombstoned=True,
    )

    assert first == second
    assert first.active is False


@pytest.mark.asyncio
async def test_sqlite_memory_lifecycle_cross_tenant_export_returns_no_payload(
    tmp_path,
) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    record = repository.commit(_memory_proposal(tenant_id="tenant-a"))
    adapter = SQLiteMemoryLifecycleAdapter(repository)

    payload = await adapter.export(
        {
            "record_id": record.memory_id,
            "tenant_id": "tenant-b",
            "source_ref": SQLiteMemoryLifecycleAdapter.source_ref(
                record.namespace,
                record.memory_id,
            ),
        }
    )
    assert payload is None

@pytest.mark.asyncio
async def test_governed_retrieval_lifecycle_is_tenant_scoped_and_exportable() -> None:
    lifecycle = DataLifecycleRegistry()
    governance = GovernanceRegistry(lifecycle)
    retrieval = GovernedRetrievalIndex(governance)
    adapter = GovernedRetrievalLifecycleAdapter(retrieval)
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("retrieval", adapter)
    adapters.register_export("retrieval", adapter)
    executor = LifecycleExecutor(lifecycle, adapters)

    first = retrieval.add(
        tenant_id="tenant-a",
        doc_id="shared-doc",
        text="alpha tenant knowledge",
        data_class="confidential",
        created_at=10.0,
    )
    second = retrieval.add(
        tenant_id="tenant-b",
        doc_id="shared-doc",
        text="beta tenant knowledge",
        created_at=11.0,
    )

    assert first.record_id != second.record_id
    assert retrieval.size("tenant-a") == 1
    assert retrieval.size("tenant-b") == 1
    assert retrieval.search("tenant-a", "alpha")[0].fragment_id == "shared-doc"
    assert retrieval.search("tenant-a", "beta") == ()

    exported = await executor.export_tenant("tenant-a")
    assert len(exported.records) == 1
    assert exported.records[0]["payload"] == {
        "record_id": first.record_id,
        "tenant_id": "tenant-a",
        "doc_id": "shared-doc",
        "text": "alpha tenant knowledge",
    }

    plan = lifecycle.request_deletion(
        "tenant-a",
        record_ids=(first.record_id,),
        now=20.0,
    )
    result = await executor.execute_deletion_plan(plan, now=21.0)

    assert result.receipts[-1].state is LifecycleState.DELETED
    assert retrieval.size("tenant-a") == 0
    assert retrieval.size("tenant-b") == 1
    assert retrieval.export_record("tenant-a", "shared-doc") is None
    assert retrieval.export_record("tenant-b", "shared-doc") is not None


@pytest.mark.asyncio
async def test_governed_retrieval_retention_physically_deletes_index_record() -> None:
    lifecycle = DataLifecycleRegistry()
    retrieval = GovernedRetrievalIndex(GovernanceRegistry(lifecycle))
    adapter = GovernedRetrievalLifecycleAdapter(retrieval)
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("retrieval", adapter)
    adapters.register_export("retrieval", adapter)
    executor = LifecycleExecutor(lifecycle, adapters)

    record = retrieval.add(
        tenant_id="tenant-a",
        doc_id="expired-doc",
        text="old retrieval material",
        created_at=10.0,
        retention_until=15.0,
    )
    assert retrieval.size("tenant-a") == 1

    results = await executor.execute_retention_expiry(now=20.0)

    assert len(results) == 1
    assert lifecycle.get(record.record_id)["state"] == "deleted"
    assert retrieval.size("tenant-a") == 0
