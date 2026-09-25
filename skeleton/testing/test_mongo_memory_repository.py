from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.memory.projection import (
    AsyncMemoryProjectionCoordinator,
    LegacyMemoryStoreProjection,
)
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk, MemoryQueryResult
from skeleton.persistence.memory_repository import (
    MemoryConflict,
    MemoryNotFound,
    MongoMemoryRepository,
)


def _matches(doc: dict, query: dict) -> bool:
    return all(doc.get(key) == value for key, value in query.items())


class FakeCursor:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]

    def sort(self, fields):
        for key, direction in reversed(fields):
            self.docs.sort(key=lambda item: item.get(key), reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        if length is None:
            return [deepcopy(doc) for doc in self.docs]
        return [deepcopy(doc) for doc in self.docs[:length]]


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.indexes: list[tuple] = []

    async def create_index(self, fields, **kwargs):
        self.indexes.append((tuple(fields), dict(kwargs)))
        return kwargs.get("name")

    async def find_one(self, query):
        for doc in self.docs:
            if _matches(doc, query):
                return deepcopy(doc)
        return None

    async def find_one_and_update(
        self,
        query,
        update,
        *,
        upsert=False,
        return_document=None,
    ):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                updated = deepcopy(doc)
                updated.update(deepcopy(update.get("$set", {})))
                self.docs[index] = updated
                return deepcopy(updated)
        if not upsert:
            return None
        created = {
            key: deepcopy(value)
            for key, value in query.items()
            if not isinstance(value, dict)
        }
        created.update(deepcopy(update.get("$setOnInsert", {})))
        created.update(deepcopy(update.get("$set", {})))
        self.docs.append(created)
        return deepcopy(created)

    async def update_one(self, query, update, *, upsert=False):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                updated = deepcopy(doc)
                updated.update(deepcopy(update.get("$set", {})))
                self.docs[index] = updated
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            created = {
                key: deepcopy(value)
                for key, value in query.items()
                if not isinstance(value, dict)
            }
            created.update(deepcopy(update.get("$setOnInsert", {})))
            created.update(deepcopy(update.get("$set", {})))
            self.docs.append(created)
            return SimpleNamespace(
                matched_count=0,
                modified_count=0,
                upserted_id=created.get("event_id") or created.get("memory_id"),
            )
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def insert_one(self, doc):
        identity = (
            doc.get("repository_namespace"),
            doc.get("memory_id"),
        )
        for existing in self.docs:
            if (
                existing.get("repository_namespace"),
                existing.get("memory_id"),
            ) == identity:
                raise RuntimeError("duplicate memory identity")
        self.docs.append(deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("memory_id"))

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def find(self, query):
        return FakeCursor(doc for doc in self.docs if _matches(doc, query))



class FakeProjectionStore(MemoryStore):
    def __init__(self):
        self.items: dict[str, MemoryChunk] = {}

    def add(self, chunk: MemoryChunk) -> None:
        self.items[chunk.id] = chunk

    def query(self, query_text, *, top_k=5, metadata_filter=None, min_score=0.0):
        return [
            MemoryQueryResult(chunk=item, score=1.0, rank=index + 1)
            for index, item in enumerate(self.items.values())
        ][:top_k]

    def delete(self, chunk_id: str) -> bool:
        return self.items.pop(chunk_id, None) is not None

    def health(self):
        return {"ok": True}


class FakeDatabase:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _now():
    return datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)


def _proposal(
    *,
    key: str,
    content: str = "remember",
    tenant: str = "tenant-a",
    namespace: str = "assistant",
    target: str | None = None,
    version: int | None = None,
    expires_at: datetime | None = None,
):
    return MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id=tenant,
        namespace=namespace,
        subject_id="user-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key=key,
        proposed_at=_now(),
        content=content,
        provenance_refs=("conversation:1",),
        source_operation_id=str(uuid4()),
        target_memory_id=target,
        expected_version=version,
        expires_at=expires_at,
    )


@pytest.mark.asyncio
async def test_mongo_repository_creates_required_unique_indexes() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)

    await repo.ensure_indexes()

    record_indexes = db["canonical_memory_records"].indexes
    idempotency_indexes = db["canonical_memory_idempotency"].indexes
    assert any(meta.get("unique") for _, meta in record_indexes)
    assert any(
        meta.get("name") == "canonical_memory_idempotency"
        and meta.get("unique") is True
        for _, meta in idempotency_indexes
    )


@pytest.mark.asyncio
async def test_mongo_repository_survives_reinstantiation_and_isolates_scope() -> None:
    db = FakeDatabase()
    first = MongoMemoryRepository(db)
    proposal = _proposal(key="create")
    stored = await first.commit(proposal, now=_now())

    reopened = MongoMemoryRepository(db)
    loaded = await reopened.get(
        stored.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )

    assert loaded == stored
    with pytest.raises(MemoryNotFound):
        await reopened.get(
            stored.memory_id,
            tenant_id="tenant-b",
            namespace="assistant",
        )
    with pytest.raises(MemoryNotFound):
        await reopened.get(
            stored.memory_id,
            tenant_id="tenant-a",
            namespace="other",
        )


@pytest.mark.asyncio
async def test_mongo_old_idempotency_receipt_survives_later_update() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    create = _proposal(key="create", content="v1")
    created = await repo.commit(create, now=_now())
    await repo.commit(
        _proposal(
            key="update",
            content="v2",
            target=created.memory_id,
            version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )

    replay = await MongoMemoryRepository(db).commit(
        create,
        now=_now() + timedelta(seconds=30),
    )
    current = await repo.get(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )

    assert replay.version == 1
    assert replay.content == "v1"
    assert current.version == 2
    assert current.content == "v2"


@pytest.mark.asyncio
async def test_mongo_update_uses_optimistic_version_fence() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    created = await repo.commit(_proposal(key="create"), now=_now())
    await repo.commit(
        _proposal(
            key="update-1",
            content="v2",
            target=created.memory_id,
            version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )

    with pytest.raises(MemoryConflict, match="version conflict"):
        await repo.commit(
            _proposal(
                key="update-stale",
                content="stale",
                target=created.memory_id,
                version=1,
            ),
            now=_now() + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_mongo_tombstone_preserves_exportable_authority() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    created = await repo.commit(_proposal(key="create"), now=_now())

    tombstoned = await repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now() + timedelta(seconds=1),
    )

    assert tombstoned.state.value == "tombstoned"
    assert tombstoned.version == 2
    with pytest.raises(MemoryNotFound):
        await repo.get(
            created.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    visible = await repo.list_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        include_tombstoned=True,
    )
    assert visible == (tombstoned,)


@pytest.mark.asyncio
async def test_mongo_idempotency_key_reuse_with_different_intent_conflicts() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    original = _proposal(key="stable", content="one")
    await repo.commit(original, now=_now())

    conflicting = _proposal(key="stable", content="two")
    with pytest.raises(MemoryConflict, match="different memory write intent"):
        await repo.commit(conflicting, now=_now())


@pytest.mark.asyncio
async def test_mongo_expire_due_tombstones_only_elapsed_records() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    due = await repo.commit(
        _proposal(
            key="due",
            content="old",
            expires_at=_now() + timedelta(seconds=5),
        ),
        now=_now(),
    )
    future = await repo.commit(
        _proposal(
            key="future",
            content="new",
            expires_at=_now() + timedelta(seconds=50),
        ),
        now=_now(),
    )

    expired = await repo.expire_due(
        tenant_id="tenant-a",
        namespace="assistant",
        now=_now() + timedelta(seconds=10),
    )

    assert [item.memory_id for item in expired] == [due.memory_id]
    assert expired[0].version == 2
    with pytest.raises(MemoryNotFound):
        await repo.get(
            due.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    assert (
        await repo.get(
            future.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    ).version == 1

@pytest.mark.asyncio
async def test_mongo_authority_rebuilds_derived_projection() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    first = await repo.commit(_proposal(key="one", content="alpha"), now=_now())
    second = await repo.commit(_proposal(key="two", content="beta"), now=_now())
    store = FakeProjectionStore()
    coordinator = AsyncMemoryProjectionCoordinator(repo)

    report = await coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(LegacyMemoryStoreProjection("rag", store),),
        known_projection_ids=("stale-id",),
    )

    assert report.degraded is False
    assert set(store.items) == {first.memory_id, second.memory_id}
    assert store.items[first.memory_id].metadata["canonical_version"] == 1
    assert store.items[first.memory_id].source_tier == "derived:rag"


@pytest.mark.asyncio
async def test_mongo_expiry_removes_projection_but_keeps_export_lineage() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    due = await repo.commit(
        _proposal(
            key="due-projection",
            content="temporary",
            expires_at=_now() + timedelta(seconds=5),
        ),
        now=_now(),
    )
    store = FakeProjectionStore()
    projection = LegacyMemoryStoreProjection("mag", store)
    coordinator = AsyncMemoryProjectionCoordinator(repo)
    await coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert due.memory_id in store.items

    report = await coordinator.expire_and_sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
        now=_now() + timedelta(seconds=10),
    )
    exported = await coordinator.export_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        include_tombstoned=True,
    )

    assert due.memory_id not in store.items
    assert report.tombstones == 1
    assert report.active_records == 0
    assert exported[0]["memory_id"] == due.memory_id
    assert exported[0]["state"] == "tombstoned"


@pytest.mark.asyncio
async def test_mongo_indexes_cover_revision_and_projection_outbox() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)

    await repo.ensure_indexes()

    revision_indexes = db["canonical_memory_revisions"].indexes
    projection_indexes = db["canonical_memory_projection_outbox"].indexes
    assert any(
        meta.get("name") == "canonical_memory_revision_identity"
        and meta.get("unique") is True
        for _, meta in revision_indexes
    )
    assert any(
        meta.get("name") == "canonical_memory_projection_event_identity"
        and meta.get("unique") is True
        for _, meta in projection_indexes
    )


@pytest.mark.asyncio
async def test_mongo_revision_history_and_projection_outbox_follow_versions() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    created = await repo.commit(_proposal(key="rev-create", content="v1"), now=_now())
    updated = await repo.commit(
        _proposal(
            key="rev-update",
            content="v2",
            target=created.memory_id,
            version=created.version,
        ),
        now=_now() + timedelta(seconds=1),
    )
    tombstoned = await repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=updated.version,
        now=_now() + timedelta(seconds=2),
    )

    history = await repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    events = await repo.pending_projection_events()

    assert [row.version for row in history] == [1, 2, 3]
    assert [row.predecessor_version for row in history] == [None, 1, 2]
    assert [row.mutation for row in history] == ["create", "update", "tombstone"]
    assert history[-1].record == tombstoned
    assert [(row.memory_version, row.action) for row in events] == [
        (1, "upsert"),
        (2, "upsert"),
        (3, "delete"),
    ]


@pytest.mark.asyncio
async def test_mongo_projection_ack_is_idempotent_and_filters_pending() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    await repo.commit(_proposal(key="projection-ack"), now=_now())
    event = (await repo.pending_projection_events())[0]

    first = await repo.mark_projection_published(
        event.event_id,
        now=_now() + timedelta(seconds=1),
    )
    second = await repo.mark_projection_published(
        event.event_id,
        now=_now() + timedelta(seconds=5),
    )

    assert first.published_at == _now() + timedelta(seconds=1)
    assert second.published_at == first.published_at
    assert await repo.pending_projection_events() == ()


@pytest.mark.asyncio
async def test_mongo_idempotent_replay_does_not_duplicate_revision_or_outbox() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    proposal = _proposal(key="replay-no-duplicate", content="v1")

    created = await repo.commit(proposal, now=_now())
    replay = await repo.commit(proposal, now=_now() + timedelta(seconds=10))

    assert replay == created
    history = await repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    events = await repo.pending_projection_events()
    assert [row.version for row in history] == [1]
    assert [(row.memory_version, row.action) for row in events] == [(1, "upsert")]


@pytest.mark.asyncio
async def test_mongo_tombstone_retry_with_original_version_heals_idempotently() -> None:
    db = FakeDatabase()
    repo = MongoMemoryRepository(db)
    created = await repo.commit(_proposal(key="delete-retry"), now=_now())

    first = await repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=created.version,
        now=_now() + timedelta(seconds=1),
    )
    retry = await repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=created.version,
        now=_now() + timedelta(seconds=10),
    )

    assert retry == first
    history = await repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    events = await repo.pending_projection_events()
    assert [row.version for row in history] == [1, 2]
    assert [(row.memory_version, row.action) for row in events] == [
        (1, "upsert"),
        (2, "delete"),
    ]


@pytest.mark.asyncio
async def test_mongo_revision_and_outbox_survive_repository_reinstantiation() -> None:
    db = FakeDatabase()
    first = MongoMemoryRepository(db)
    created = await first.commit(_proposal(key="restart-history", content="v1"), now=_now())
    await first.commit(
        _proposal(
            key="restart-update",
            content="v2",
            target=created.memory_id,
            version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )
    first_event = (await first.pending_projection_events())[0]
    await first.mark_projection_published(
        first_event.event_id,
        now=_now() + timedelta(seconds=2),
    )

    reopened = MongoMemoryRepository(db)
    history = await reopened.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    pending = await reopened.pending_projection_events()

    assert [row.record.content for row in history] == ["v1", "v2"]
    assert [(row.memory_version, row.action) for row in pending] == [(2, "upsert")]
