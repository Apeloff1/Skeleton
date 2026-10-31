"""Majority-durable source epoch concurrency, crash and role-scoped fences."""

import asyncio
from types import SimpleNamespace

import pytest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError, fence_conversation_write,
)


class Collection:
    def __init__(self):
        self.records = {}
        self.lock = asyncio.Lock()

    async def insert_one(self, record):
        async with self.lock:
            if record["_id"] in self.records:
                raise ValueError("duplicate")
            self.records[record["_id"]] = dict(record)
        return SimpleNamespace(inserted_id=record["_id"])

    async def find_one(self, query):
        async with self.lock:
            record = self.records.get(query["_id"])
            if record is None or any(record.get(k) != v for k, v in query.items()):
                return None
            return dict(record)

    async def find_one_and_update(self, query, update, *, return_document):
        async with self.lock:
            record = self.records.get(query["_id"])
            if record is None or any(record.get(k) != v for k, v in query.items()):
                return None
            for key, delta in update.get("$inc", {}).items():
                record[key] += delta
            record.update(update.get("$set", {}))
            return dict(record)


class Database:
    def __init__(self):
        self.collection = Collection()
        self.received = None

    def get_collection(self, name, *, read_concern, write_concern):
        assert name == "canonical_source_epochs"
        assert read_concern.level == "majority"
        assert write_concern.document.get("w") == "majority"
        self.received = True
        return self.collection


def epoch():
    return MongoCanonicalSourceEpoch(Database())


async def read(owner, tenant="tenant", actor="actor", context="context"):
    return await owner.read_epoch(
        tenant_id=tenant, actor_id=actor, context_id=context,
    )


@pytest.mark.asyncio
async def test_durable_writer_epoch_requires_operator_migration_and_is_monotonic():
    owner = epoch()
    with pytest.raises(MongoSourceEpochError):
        await read(owner)
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    assert await read(owner) == 2
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        with pytest.raises(MongoSourceEpochError, match="writing"):
            await read(owner)
    assert await read(owner) == 4
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            with pytest.raises(MongoSourceEpochError):
                await read(owner)
    assert await read(owner) == 6


@pytest.mark.asyncio
async def test_reader_and_other_writers_reject_inflight_epoch():
    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    entered, release = asyncio.Event(), asyncio.Event()

    async def writer():
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            entered.set()
            await release.wait()

    task = asyncio.create_task(writer())
    await entered.wait()
    with pytest.raises(MongoSourceEpochError):
        await read(owner)
    with pytest.raises(MongoSourceEpochError):
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            pass
    release.set()
    await task
    assert await read(owner) == 4


@pytest.mark.asyncio
async def test_failed_mutation_quarantines_epoch_until_manual_reconciliation():
    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    with pytest.raises(ValueError):
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            raise ValueError("injected partial mutation")
    with pytest.raises(MongoSourceEpochError, match="writing"):
        await read(owner)
    with pytest.raises(MongoSourceEpochError):
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            pass


@pytest.mark.asyncio
async def test_writer_scope_cannot_be_inherited_into_child_task():
    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        async def stolen():
            with pytest.raises(MongoSourceEpochError, match="inherited"):
                async with owner.writer(tenant_id="tenant", actor_id="actor"):
                    pass
        await asyncio.create_task(stolen())


@pytest.mark.asyncio
async def test_actual_conversation_write_decorator_surrounds_awaitable_owner_mutation():
    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")

    class Repo:
        canonical_source_epoch = owner

        @fence_conversation_write
        async def append_message(self, *, tenant_id, owner_id):
            with pytest.raises(MongoSourceEpochError, match="writing"):
                await read(owner)
            return "persisted"

    assert await Repo().append_message(tenant_id="tenant", owner_id="actor") == "persisted"
    assert await read(owner) == 4
    with pytest.raises(MongoSourceEpochError):
        await Repo().append_message(tenant_id="foreign", owner_id="actor")


@pytest.mark.asyncio
async def test_governed_tenant_retirement_denied_until_multi_actor_custody_exists():
    # A tenant-wide deletion can touch multiple actors and separate owners.
    # Never allow one actor's epoch to claim it has fenced every target.
    from core.conversations import MongoConversationAuthority, ConversationStorageUnavailable

    conversation = object.__new__(MongoConversationAuthority)
    conversation.canonical_source_epoch = epoch()
    with pytest.raises(ConversationStorageUnavailable, match="cross-owner retirement"):
        await conversation.execute_governed_deletion(tenant_id="tenant")
    with pytest.raises(ConversationStorageUnavailable, match="cross-owner retirement"):
        await conversation.execute_due_retention(tenant_id="tenant")

@pytest.mark.asyncio
async def test_rejected_protected_thread_deletion_does_not_quarantine_writer_epoch():
    """Denied no-write operations must not poison the majority-durable fence."""
    from core.conversations import MongoConversationAuthority, ConversationStorageUnavailable

    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    conversation = object.__new__(MongoConversationAuthority)
    conversation.canonical_source_epoch = owner

    with pytest.raises(ConversationStorageUnavailable, match="cross-owner retirement"):
        await conversation.delete_thread_with_governance(
            "thread", tenant_id="tenant", owner_id="actor",
            expected_thread_version=1,
        )
    assert await read(owner) == 2
    # A subsequent legitimate writer still acquires and commits normally.
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        with pytest.raises(MongoSourceEpochError, match="writing"):
            await read(owner)
    assert await read(owner) == 4


@pytest.mark.asyncio
async def test_protected_internal_conversation_recovery_rejects_unfenced_caller():
    """Prepared WAL repair is a canonical mutation, even when called internally."""
    from unittest.mock import AsyncMock
    from core.conversations import MongoConversationAuthority

    owner = epoch()
    conversation = object.__new__(MongoConversationAuthority)
    conversation.canonical_source_epoch = owner
    conversation.get_thread = AsyncMock(return_value="verified-thread")
    conversation.messages = SimpleNamespace(find_one=AsyncMock(return_value=None))
    with pytest.raises(MongoSourceEpochError, match="owner-scoped epoch"):
        await conversation._recover_prepared(
            "thread", tenant_id="tenant", owner_id="actor",
        )
    assert conversation.get_thread.await_count == 0
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        assert await conversation._recover_prepared(
            "thread", tenant_id="tenant", owner_id="actor",
        ) == "verified-thread"
    assert await read(owner) == 4


@pytest.mark.asyncio
async def test_internal_mongo_memory_mutations_require_same_actor_writer_epoch():
    """Public decorators cannot be bypassed via low-level reservation helpers."""
    from datetime import datetime, timezone
    from skeleton.persistence.memory_repository import MongoMemoryRepository

    owner = epoch()
    memory = object.__new__(MongoMemoryRepository)
    memory.canonical_source_epoch = owner
    proposal = SimpleNamespace(tenant_id="tenant", subject_id="actor")
    record = SimpleNamespace(tenant_id="tenant", subject_id="actor")
    now = datetime.now(timezone.utc)
    operations = (
        lambda: memory._ensure_revision_and_projection(
            record, mutation="create", predecessor_version=None,
            projection_action="upsert", committed_at=now,
        ),
        lambda: memory._recover_reservation(proposal, {}),
        lambda: memory._reserve(proposal, memory_id="memory", instant=now),
        lambda: memory._release_failed_reservation(proposal, "token"),
        lambda: memory._commit_reservation(proposal, "token", record),
    )
    for operation in operations:
        with pytest.raises(MongoSourceEpochError, match="owner-scoped epoch"):
            await operation()

    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        # A no-write replay token is admitted only under the same real writer.
        await memory._release_failed_reservation(proposal, "replay")
        with pytest.raises(MongoSourceEpochError, match="owner-scoped epoch"):
            memory._require_canonical_writer(tenant_id="tenant", actor_id="other")
    assert await read(owner) == 4


@pytest.mark.asyncio
async def test_stable_epoch_with_residual_writer_token_is_quarantined():
    """An apparently even epoch is not readable if an old writer still owns it."""
    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    assert await read(owner) == 2
    key = owner._key("tenant", "actor")
    doc = owner._collection.records[key]
    doc["writer_token"] = "orphaned-owner"
    with pytest.raises(MongoSourceEpochError, match="quarantined"):
        await read(owner)
    with pytest.raises(MongoSourceEpochError):
        async with owner.writer(tenant_id="tenant", actor_id="actor"):
            pass
    assert doc["epoch"] == 2


@pytest.mark.asyncio
async def test_protected_memory_update_requires_subject_match_in_final_cas():
    """A record reassigned after the initial read must not be overwritten."""
    from skeleton.persistence.memory_repository import MemoryConflict, MongoMemoryRepository
    from skeleton.testing.test_mongo_memory_repository import FakeDatabase, _proposal, _now

    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant-a", actor_id="user-a")
    db = FakeDatabase()
    repo = MongoMemoryRepository(db, canonical_source_epoch=owner)
    created = await repo.commit(_proposal(key="first"), now=_now())
    records = db["canonical_memory_records"]
    original_find_one_and_update = records.find_one_and_update
    captured = []

    async def concurrent_subject_change(query, update, **kwargs):
        captured.append(dict(query))
        # An independently administered/external mutation is not protected
        # by our actor epoch: deny rather than overwriting another actor.
        for doc in records.docs:
            if doc.get("memory_id") == created.memory_id:
                doc["subject_id"] = "foreign-actor"
        return await original_find_one_and_update(query, update, **kwargs)

    records.find_one_and_update = concurrent_subject_change
    with pytest.raises(MemoryConflict, match="version conflict"):
        await repo.commit(
            _proposal(key="second", content="changed",
                      target=created.memory_id, version=created.version),
            now=_now(),
        )
    assert len(captured) == 1
    assert captured[0]["subject_id"] == "user-a"
    assert records.docs[0]["version"] == created.version
    assert records.docs[0]["subject_id"] == "foreign-actor"
    with pytest.raises(MongoSourceEpochError, match="quarantined"):
        await read(owner, tenant="tenant-a", actor="user-a")


@pytest.mark.asyncio
async def test_protected_memory_tombstone_rechecks_actor_under_writer_epoch():
    """The actor selected before the writer lock cannot change unnoticed."""
    from dataclasses import replace
    from unittest.mock import AsyncMock
    from skeleton.persistence.memory_repository import MongoMemoryRepository
    from skeleton.testing.test_mongo_memory_repository import FakeDatabase, _proposal, _now

    owner = epoch()
    await owner.provision_migration_epoch(tenant_id="tenant-a", actor_id="user-a")
    db = FakeDatabase()
    repo = MongoMemoryRepository(db, canonical_source_epoch=owner)
    record = await repo.commit(_proposal(key="first"), now=_now())
    original = repo.get
    repo.get = AsyncMock(side_effect=(
        record,
        replace(record, subject_id="foreign-actor"),
    ))
    with pytest.raises(MongoSourceEpochError, match="owner-scoped epoch"):
        await repo.tombstone(
            record.memory_id, tenant_id="tenant-a",
            namespace="assistant", expected_version=record.version,
        )
    # No tombstone CAS or revision side effect could execute.
    assert db["canonical_memory_records"].docs[0]["state"] == "active"
    assert db["canonical_memory_records"].docs[0]["version"] == record.version
    repo.get = original
    with pytest.raises(MongoSourceEpochError, match="quarantined"):
        await read(owner, tenant="tenant-a", actor="user-a")


@pytest.mark.asyncio
async def test_memento_publish_and_retirement_require_canonical_actor_epoch():
    """Sidecar writes must not bypass the same conversation-source custody."""
    from unittest.mock import AsyncMock
    from skeleton.context.sealed_memento import MementoCatalogHead, MementoRecord, SealedMementoArchive
    from skeleton.context.sealed_sandwich import ContextBinding, ContextSandwichCodec
    from skeleton.persistence.mongo_memento_repository import MongoMementoAuthority

    owner = epoch()
    mongo = object.__new__(MongoMementoAuthority)
    mongo.conversation = SimpleNamespace(
        canonical_source_epoch=owner,
        memento_witness=SimpleNamespace(read=AsyncMock(), compare_and_set=AsyncMock()),
        _admit_storage=AsyncMock(),
    )
    binding = ContextBinding("tenant", "actor", "thread", "local", "policy")
    archive = SealedMementoArchive(
        ContextSandwichCodec({"key": b"k" * 32}, active_key_id="key"), binding,
    )
    genesis = MementoCatalogHead()
    ciphertext, _ = archive.seal(MementoRecord(1, "user", b"message"), previous=genesis)
    assert getattr(MongoMementoAuthority.publish, "__canonical_source_writer_fence__") == "memento"
    assert getattr(MongoMementoAuthority.retire_thread, "__canonical_source_writer_fence__") == "memento"
    with pytest.raises(MongoSourceEpochError, match="witnessed handoff"):
        await mongo.publish(
            archive=archive, expected_head=genesis, expected_thread_version=1,
            stream="user", ciphertext=ciphertext, custody_mode="witnessed",
        )
    with pytest.raises(MongoSourceEpochError, match="writer epoch not owned|admission unavailable"):
        await mongo.retire_thread(tenant_id="tenant", owner_id="actor", thread_id="thread")
    assert mongo.conversation._admit_storage.await_count == 0

    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    # A protected actor cannot publish a legacy archive, even when it has a
    # usable writer epoch and the raw memento primitive is reachable.
    with pytest.raises(MongoSourceEpochError, match="witnessed custody"):
        await mongo.publish(
            archive=archive, expected_head=genesis, expected_thread_version=1,
            stream="user", ciphertext=ciphertext,
        )
    assert await read(owner) == 2
    # A claimed witnessed write without a bound external witness also denies
    # before acquiring the actor epoch.
    saved = mongo.conversation.memento_witness
    mongo.conversation.memento_witness = None
    with pytest.raises(MongoSourceEpochError, match="independent witness"):
        await mongo.publish(
            archive=archive, expected_head=genesis, expected_thread_version=1,
            stream="user", ciphertext=ciphertext, custody_mode="witnessed",
        )
    mongo.conversation.memento_witness = saved
    assert await read(owner) == 2
    with pytest.raises(MongoSourceEpochError, match="witnessed handoff"):
        await mongo.publish(
            archive=archive, expected_head=genesis, expected_thread_version=1,
            stream="user", ciphertext=ciphertext, custody_mode="witnessed",
        )
    assert await read(owner) == 2
    # The test deliberately leaves the mutation method unimplemented: only the
    # ownership preflight is under test. Denied calls never begin Mongo writes.
    with pytest.raises(MongoSourceEpochError, match="actor missing"):
        await mongo.retire_thread(tenant_id="tenant", owner_id=None, thread_id="thread")
    with pytest.raises(MongoSourceEpochError, match="thread missing"):
        await mongo.retire_thread(tenant_id="tenant", owner_id="actor", thread_id=None)
    assert await read(owner) == 2
