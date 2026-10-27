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
