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
    with pytest.raises(MongoSourceEpochError, match="actor"):
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
        with pytest.raises(MongoSourceEpochError, match="actor"):
            await operation()

    await owner.provision_migration_epoch(tenant_id="tenant", actor_id="actor")
    async with owner.writer(tenant_id="tenant", actor_id="actor"):
        # A no-write replay token is admitted only under the same real writer.
        await memory._release_failed_reservation(proposal, "replay")
        with pytest.raises(MongoSourceEpochError, match="actor"):
            memory._require_canonical_writer(tenant_id="tenant", actor_id="other")
    assert await read(owner) == 4
