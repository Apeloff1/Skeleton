"""Journaled-majority real canonical epoch source contract (source-only).

An async in-memory recording collection implements the same Mongo atomic
findOneAndUpdate behavior. No Docker host, production database, actor data,
lease installation or network is accessed.
"""
from __future__ import annotations

import asyncio
import copy
from functools import wraps

import pytest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)

TENANT = "synthetic-tenant"
ACTOR = "synthetic-actor"


def _run_async(callback):
    @wraps(callback)
    def runner(*args, **kwargs):
        return asyncio.run(callback(*args, **kwargs))
    return runner


class FakeReadCollection:
    def __init__(self, writer):
        self.writer = writer
        self.reads = []

    async def find_one(self, query, **kwargs):
        self.reads.append((copy.deepcopy(query), kwargs))
        return copy.deepcopy(self.writer.rows.get(query["_id"]))


class FakeJournalCollection:
    def __init__(self):
        self.rows = {}
        self.operations = []
        self.after_update_failure = False
        self.before_update_failure = False

    async def find_one(self, query, **kwargs):
        return copy.deepcopy(self.rows.get(query["_id"]))

    async def insert_one(self, row):
        self.rows[row["_id"]] = copy.deepcopy(row)
        return {"acknowledged": True}

    async def find_one_and_update(self, query, changes, *, return_document):
        self.operations.append((copy.deepcopy(query), copy.deepcopy(changes)))
        if self.before_update_failure:
            raise TimeoutError("synthetic private Mongo connection password")
        old = self.rows.get(query["_id"])
        if not isinstance(old, dict) or any(old.get(k) != v
                                             for k, v in query.items()):
            return None
        next_row = copy.deepcopy(old)
        for k, amount in changes["$inc"].items():
            next_row[k] += amount
        next_row.update(changes["$set"])
        self.rows[query["_id"]] = next_row
        if self.after_update_failure:
            raise TimeoutError("synthetic private Mongo connection password")
        return copy.deepcopy(next_row)


class FakeDatabase:
    def __init__(self):
        self.write = FakeJournalCollection()
        self.reader = FakeReadCollection(self.write)
        self.options = []

    def get_collection(self, name, **kwargs):
        assert name == "canonical_source_epochs"
        self.options.append(kwargs)
        return self.reader if kwargs["read_concern"].level == "linearizable" else self.write


def _epoch(*, with_actor=True):
    database = FakeDatabase()
    epoch = MongoCanonicalSourceEpoch(database)
    if with_actor:
        key = epoch._key(TENANT, ACTOR)
        database.write.rows[key] = {
            "_id": key, "tenant_id": TENANT, "actor_id": ACTOR,
            "phase": "stable", "writer_token": None, "epoch": 2,
        }
    return epoch, database


def test_journaled_majority_is_explicit_not_inferred_from_global_policy():
    epoch, db = _epoch()
    assert type(epoch) is MongoCanonicalSourceEpoch
    assert db.options[0]["write_concern"].document == {
        "w": "majority", "j": True, "wtimeout": 10000,
    }
    assert db.options[0]["read_concern"].level == "majority"
    assert db.options[1]["read_concern"].level == "linearizable"
    assert str(db.options[1]["read_preference"]) == "Primary()"
    assert str(db.options[0]["read_preference"]) == "Primary()"


@_run_async
async def test_real_epoch_source_writer_cas_is_odd_even_and_token_bound():
    epoch, database = _epoch()
    async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
        epoch.require_actor_writer(tenant_id=TENANT, actor_id=ACTOR)
        doc = next(iter(database.write.rows.values()))
        assert doc["epoch"] == 3
        assert doc["phase"] == "writing"
        assert isinstance(doc["writer_token"], str)
    doc = next(iter(database.write.rows.values()))
    assert doc["epoch"] == 4
    assert doc["phase"] == "stable"
    assert doc["writer_token"] is None
    assert len(database.write.operations) == 2
    first, final = database.write.operations
    assert first[0]["phase"] == "stable"
    assert first[0]["writer_token"] is None
    assert final[0]["phase"] == "writing"
    assert final[0]["epoch"] == 3
    assert final[0]["writer_token"] != first[0]["writer_token"]
    assert first[1]["$inc"] == final[1]["$inc"] == {"epoch": 1}
    assert await epoch.read_epoch(
        tenant_id=TENANT, actor_id=ACTOR, context_id="synthetic-context",
    ) == 4


@_run_async
async def test_competing_process_writer_is_denied_during_real_source_epoch():
    epoch, database = _epoch()
    async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
        async def attempt():
            with pytest.raises(MongoSourceEpochError, match="cannot be inherited"):
                async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
                    pytest.fail("competing writer reached protected mutation")
        await asyncio.create_task(attempt())
        assert database.write.rows[epoch._key(TENANT, ACTOR)]["epoch"] == 3
    assert database.write.rows[epoch._key(TENANT, ACTOR)]["epoch"] == 4


@_run_async
async def test_cross_task_inherited_context_cannot_write_unowned_actor():
    epoch, _ = _epoch()
    async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
        async def child():
            with pytest.raises(MongoSourceEpochError, match="owner-scoped"):
                epoch.require_actor_writer(tenant_id=TENANT, actor_id=ACTOR)
            with pytest.raises(MongoSourceEpochError, match="inherited"):
                async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
                    pytest.fail("inherited task escalated")
        await asyncio.create_task(child())


@_run_async
async def test_missing_epoch_never_provisions_it_implicitly():
    epoch, database = _epoch(with_actor=False)
    with pytest.raises(MongoSourceEpochError, match="not owned"):
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            pytest.fail("unmigrated actor should not be writable")
    assert database.write.rows == {}
    assert len(database.write.operations) == 1


@_run_async
async def test_failed_protected_write_quarantines_actor_and_blocks_next_writer():
    epoch, database = _epoch()
    with pytest.raises(RuntimeError, match="synthetic mutation failure"):
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            raise RuntimeError("synthetic mutation failure")
    doc = database.write.rows[epoch._key(TENANT, ACTOR)]
    assert doc["phase"] == "writing" and doc["epoch"] == 3
    with pytest.raises(MongoSourceEpochError, match="not owned"):
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            pytest.fail("crashed actor must remain quarantined")


@_run_async
async def test_uncertain_journal_ack_never_admits_writer_and_may_quarantine():
    epoch, database = _epoch()
    database.write.after_update_failure = True
    with pytest.raises(MongoSourceEpochError, match="admission unavailable") as error:
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            pytest.fail("no uncertain write can authorize user mutation")
    assert "private Mongo" not in str(error.value)
    assert database.write.rows[epoch._key(TENANT, ACTOR)]["epoch"] == 3
    assert database.write.rows[epoch._key(TENANT, ACTOR)]["phase"] == "writing"


@_run_async
async def test_uncertain_commit_ack_does_not_claim_success():
    epoch, database = _epoch()
    with pytest.raises(MongoSourceEpochError, match="completion unavailable"):
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            database.write.after_update_failure = True
    # Simulate the database actually performing the CAS before reply was lost.
    # It is still unsafe to claim the operation completed from this client.
    assert database.write.rows[epoch._key(TENANT, ACTOR)]["epoch"] == 4
    assert database.write.rows[epoch._key(TENANT, ACTOR)]["phase"] == "stable"


@_run_async
async def test_writer_cancellation_preserves_quarantine():
    epoch, database = _epoch()
    async def interrupted():
        async with epoch.writer(tenant_id=TENANT, actor_id=ACTOR):
            raise asyncio.CancelledError("synthetic cancellation")
    with pytest.raises(asyncio.CancelledError):
        await interrupted()
    doc = database.write.rows[epoch._key(TENANT, ACTOR)]
    assert doc["epoch"] == 3
    assert doc["phase"] == "writing"


def test_source_epoch_writers_have_bounded_mongo_ack_windows():
    import inspect
    source = inspect.getsource(MongoCanonicalSourceEpoch.writer)
    assert 'asyncio.timeout(12)' in source
    assert 'find_one_and_update' in source
    assert 'canonical writer completion unavailable' in source

def test_real_memento_archive_and_retirement_cas_are_explicitly_journaled():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "skeleton/persistence/mongo_memento_repository.py"
    ).read_text(encoding="utf-8")
    assert 'WriteConcern(w="majority", j=True)' in source
    assert source.count('WriteConcern(w="majority", j=True)') == 2
    assert 'WriteConcern(w="majority")' not in source
    assert 'with_options(write_concern=majority)' in source
