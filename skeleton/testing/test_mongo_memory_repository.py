from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
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

    async def update_one(self, query, update):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                updated = deepcopy(doc)
                updated.update(deepcopy(update.get("$set", {})))
                self.docs[index] = updated
                return SimpleNamespace(matched_count=1, modified_count=1)
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
