"""Driver-independent Mongo transaction conformance and failure-injection checks."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import sys
from types import ModuleType, SimpleNamespace

import pytest

from skeleton.context.sealed_memento import MementoCatalogHead, MementoRecord, SealedMementoArchive
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextIntegrityError,
)
from skeleton.persistence.mongo_memento_repository import (
    MongoMementoAuthority, MongoMementoConflict, MongoMementoUnavailable,
    memento_retirement_requires_witness,
)


class FakeSession:
    def __init__(self, database):
        self.db = database
        self.rows = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def start_transaction(self, **kw):
        assert kw["write_concern"].w == "majority"
        assert kw["read_concern"].level == "snapshot"
        return self

    async def __enter_transaction(self):
        self.rows = deepcopy(self.db.rows)
        return self

    async def __exit_transaction(self, error_type, *_):
        if error_type is None:
            if self.db.fail_commit:
                raise RuntimeError("no majority ack")
            self.db.rows = self.rows
        return False

    # Nested async with calls this same context manager twice; distinguish
    # session lifecycle from transaction enter/leave.
    async def __aenter__(self):
        if self.rows is None:
            self.rows = deepcopy(self.db.rows)
        return self

    async def __aexit__(self, error_type, *_):
        if error_type is None:
            if self.db.fail_commit:
                raise RuntimeError("commit failed")
            self.db.rows = self.rows
        return False


class FakeCollection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def with_options(self, **options):
        assert options["write_concern"].w == "majority"
        return self

    def _rows(self, session):
        return (session.rows if session is not None else self.db.rows)[self.name]

    async def create_index(self, *a, **kw):
        return kw["name"]

    async def find_one(self, query, *, session=None):
        for row in self._rows(session).values():
            if matches(row, query):
                return deepcopy(row)
        return None

    async def insert_one(self, row, *, session):
        rows = self._rows(session)
        if row["_id"] in rows:
            raise RuntimeError("duplicate unique key")
        rows[row["_id"]] = deepcopy(row)

    async def update_one(self, query, update, *, session=None):
        for key, row in self._rows(session).items():
            if matches(row, query):
                row.update(deepcopy(update["$set"]))
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def delete_many(self, query):
        matches_ = [key for key, row in self._rows(None).items() if matches(row, query)]
        for key in matches_:
            del self._rows(None)[key]
        return SimpleNamespace(deleted_count=len(matches_))

    def find(self, query, *, session):
        return FakeCursor([deepcopy(row) for row in self._rows(session).values()
                           if matches(row, query)])


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, field, direction):
        assert direction == 1
        self.rows.sort(key=lambda row: row[field])
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, *, length):
        return self.rows[:length]


def matches(row, predicate):
    for key, expected in predicate.items():
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$exists" in expected and (key in row) != expected["$exists"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$gt" in expected and not actual > expected["$gt"]:
                return False
            if "$lte" in expected and not actual <= expected["$lte"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeDatabase:
    def __init__(self):
        self.rows = {"conversation_threads": {}, "conversation_memento_frames": {}}
        self.client = self
        self.fail_commit = False
        self.supports_sessions = True

    def __getitem__(self, key):
        return FakeCollection(self, key)

    async def start_session(self):
        if not self.supports_sessions:
            raise RuntimeError("standalone server")
        return FakeSession(self)


class Authority:
    def __init__(self):
        self.database = FakeDatabase()
        self.threads = self.database["conversation_threads"]
        self.storage_calls = 0

    async def get_thread(self, *_a, **_k):
        raise AssertionError("do not read canonical state outside transaction")

    async def _admit_storage(self, **kwargs):
        assert kwargs["resource_id"] == "conversation-memento"
        self.storage_calls += 1


@pytest.fixture(autouse=True)
def fake_pymongo(monkeypatch):
    pymongo = ModuleType("pymongo")
    read = ModuleType("pymongo.read_concern")
    write = ModuleType("pymongo.write_concern")
    read.ReadConcern = lambda level: SimpleNamespace(level=level)
    write.WriteConcern = lambda w, **kwargs: SimpleNamespace(w=w, document={"w": w, **kwargs})
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)
    monkeypatch.setitem(sys.modules, "pymongo.read_concern", read)
    monkeypatch.setitem(sys.modules, "pymongo.write_concern", write)


@pytest.fixture
def suite():
    owner = Authority()
    owner.database.rows["conversation_threads"]["t1"] = {
        "_id": "t1", "tenant_id": "tenant", "owner_id": "owner",
        "version": 3, "state": "active",
    }
    binding = ContextBinding("tenant", "owner", "t1", "local", "policy")
    evidence = {"artifact:1": sha256(b"real output").hexdigest()}
    archive = SealedMementoArchive(
        ContextSandwichCodec({"key": b"k" * 32}, active_key_id="key"), binding,
        work_verifier=lambda ref, digest, data: evidence.get(ref) == digest
        and sha256(data).hexdigest() == digest,
    )
    return owner, MongoMementoAuthority(owner), archive, evidence


def publish(db, archive, record):
    async def run():
        previous = await db.trusted_head(archive=archive)
        wire, expected = archive.seal(record, previous=previous)
        head = await db.publish(
            archive=archive, expected_head=previous, expected_thread_version=3,
            stream=record.stream, ciphertext=wire,
        )
        assert head == expected
        return wire, expected
    return asyncio.run(run())


def test_transaction_and_verified_three_stream_replay(suite):
    owner, db, archive, _ = suite
    asyncio.run(db.ensure_indexes())
    publish(db, archive, MementoRecord(1, "user", b"build"))
    publish(db, archive, MementoRecord(2, "llm", b"done", causal_serial=1))
    publish(db, archive, MementoRecord(
        3, "work", b"real output", causal_serial=1,
        evidence_ref="artifact:1", evidence_digest=sha256(b"real output").hexdigest(),
    ))
    page = asyncio.run(db.read_window(archive=archive))
    assert [r.stream for r in page.records] == ["user", "llm", "work"]
    assert not page.has_more and page.authoritative_head == page.verified_head
    assert owner.storage_calls == 3


def test_stale_head_version_and_owner_fail_closed(suite):
    owner, db, archive, _ = suite
    publish(db, archive, MementoRecord(1, "user", b"ok"))
    fake, _ = archive.seal(MementoRecord(1, "user", b"other"), previous=MementoCatalogHead())
    with pytest.raises(MongoMementoConflict):
        asyncio.run(db.publish(archive=archive, expected_head=MementoCatalogHead(),
                               expected_thread_version=3, stream="user", ciphertext=fake))
    head = asyncio.run(db.trusted_head(archive=archive))
    wire, _ = archive.seal(MementoRecord(2, "llm", b"next"), previous=head)
    with pytest.raises(MongoMementoConflict):
        asyncio.run(db.publish(archive=archive, expected_head=head,
                               expected_thread_version=2, stream="llm", ciphertext=wire))
    intruder = SealedMementoArchive(archive.codec, replace(archive.binding, tenant_id="other"))
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(db.trusted_head(archive=intruder))
    assert len(owner.database.rows["conversation_memento_frames"]) == 1


def test_failed_majority_commit_and_missing_transactions_do_not_publish(suite):
    owner, db, archive, _ = suite
    owner.database.fail_commit = True
    head = MementoCatalogHead()
    wire, _ = archive.seal(MementoRecord(1, "user", b"never commit"), previous=head)
    with pytest.raises(MongoMementoUnavailable):
        asyncio.run(db.publish(archive=archive, expected_head=head,
                               expected_thread_version=3, stream="user", ciphertext=wire))
    assert not owner.database.rows["conversation_memento_frames"]
    assert "_sealed_memento_head" not in owner.database.rows["conversation_threads"]["t1"]
    owner.database.fail_commit = False
    owner.database.supports_sessions = False
    with pytest.raises(MongoMementoUnavailable):
        asyncio.run(db.publish(archive=archive, expected_head=head,
                               expected_thread_version=3, stream="user", ciphertext=wire))


def test_tamper_truncated_and_revoked_evidence_rejected(suite):
    owner, db, archive, evidence = suite
    publish(db, archive, MementoRecord(1, "user", b"saved"))
    publish(db, archive, MementoRecord(
        2, "work", b"real output", evidence_ref="artifact:1",
        evidence_digest=sha256(b"real output").hexdigest(),
    ))
    assert len(asyncio.run(db.read_window(archive=archive)).records) == 2
    evidence.clear()
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(db.read_window(archive=archive))
    evidence["artifact:1"] = sha256(b"real output").hexdigest()
    first = owner.database.rows["conversation_memento_frames"]["t1:1"]
    first["ciphertext"] = first["ciphertext"].replace(b"ciphertext", b"CIPHERtext")
    with pytest.raises((SealedContextIntegrityError, ValueError)):
        asyncio.run(db.read_window(archive=archive))


def test_retired_archive_blocks_all_resumption(suite):
    owner, db, archive, _ = suite
    owner.database.rows["conversation_threads"]["t1"]["_sealed_memento_retired"] = True
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(db.read_window(archive=archive))


def test_governed_retirement_fences_archive_and_erases_frames(suite):
    owner, db, archive, _ = suite
    publish(db, archive, MementoRecord(1, "user", b"private"))
    removed = asyncio.run(db.retire_thread(
        tenant_id="tenant", owner_id="owner", thread_id="t1"
    ))
    assert removed == 1
    assert not owner.database.rows["conversation_memento_frames"]
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(db.trusted_head(archive=archive))
    with pytest.raises(SealedContextBoundaryError):
        asyncio.run(db.retire_thread(
            tenant_id="tenant", owner_id="intruder", thread_id="t1"
        ))

def test_pinned_mongo_cursor_rejects_tampered_saved_checkpoint(suite):
    from skeleton.context.sealed_memento import encode_catalog_head
    owner, db, archive, _ = suite
    publish(db, archive, MementoRecord(1, "user", b"first"))
    publish(db, archive, MementoRecord(2, "llm", b"second", causal_serial=1))
    page = asyncio.run(db.read_window(archive=archive, limit=1))
    valid = asyncio.run(db.read_window(
        archive=archive, after_serial=1, expected_starting_head=page.verified_head,
    ))
    assert [r.serial for r in valid.records] == [2]
    replaced = replace(page.verified_head, commitment="a" * 64)
    owner.database.rows["conversation_memento_frames"]["t1:1"]["head_blob"] = (
        encode_catalog_head(replaced)
    )
    with pytest.raises(MongoMementoConflict):
        asyncio.run(db.read_window(
            archive=archive, after_serial=1, expected_starting_head=page.verified_head,
        ))


def test_witnessed_custody_is_durable_and_cannot_be_silently_downgraded(suite):
    owner, db, archive, _ = suite

    async def scenario():
        genesis = MementoCatalogHead()
        wire, head = archive.seal(MementoRecord(1, "user", b"protected"), previous=genesis)
        assert await db.publish(
            archive=archive, expected_head=genesis, expected_thread_version=3,
            stream="user", ciphertext=wire, custody_mode="witnessed",
        ) == head
        thread = owner.database.rows["conversation_threads"]["t1"]
        assert thread["_sealed_memento_custody"] == "witnessed"
        assert memento_retirement_requires_witness(thread, witness_present=True)
        wire2, _ = archive.seal(MementoRecord(2, "user", b"protected-2"), previous=head)
        with pytest.raises(MongoMementoConflict, match="custody"):
            await db.publish(
                archive=archive, expected_head=head, expected_thread_version=3,
                stream="user", ciphertext=wire2,
            )
        assert len(owner.database.rows["conversation_memento_frames"]) == 1
        assert owner.database.rows["conversation_threads"]["t1"]["_sealed_memento_head"]

    asyncio.run(scenario())


def test_retirement_refuses_missing_invalid_or_unavailable_witness():
    with pytest.raises(MongoMementoUnavailable, match="custody"):
        memento_retirement_requires_witness({}, witness_present=False)
    with pytest.raises(MongoMementoUnavailable, match="custody"):
        memento_retirement_requires_witness(
            {"_sealed_memento_custody": "unknown"}, witness_present=True,
        )
    with pytest.raises(MongoMementoUnavailable, match="independent"):
        memento_retirement_requires_witness(
            {"_sealed_memento_custody": "witnessed"}, witness_present=False,
        )
    assert not memento_retirement_requires_witness(
        {"_sealed_memento_custody": "legacy"}, witness_present=False,
    )
    assert memento_retirement_requires_witness(
        {"_sealed_memento_custody": "witnessed"}, witness_present=True,
    )


def test_custody_cannot_be_reclassified_between_publications(suite):
    owner, db, archive, _ = suite
    publish(db, archive, MementoRecord(1, "user", b"legacy"))
    assert owner.database.rows["conversation_threads"]["t1"]["_sealed_memento_custody"] == "legacy"

    async def scenario():
        head = await db.trusted_head(archive=archive)
        wire, _ = archive.seal(MementoRecord(2, "user", b"upgrade"), previous=head)
        with pytest.raises(MongoMementoConflict, match="custody"):
            await db.publish(
                archive=archive, expected_head=head, expected_thread_version=3,
                stream="user", ciphertext=wire, custody_mode="witnessed",
            )
    asyncio.run(scenario())
    assert len(owner.database.rows["conversation_memento_frames"]) == 1


def test_witness_configured_canonical_owner_denies_legacy_publication(suite):
    owner, db, archive, _ = suite
    owner.memento_witness = object()

    async def scenario():
        before = MementoCatalogHead()
        wire, _ = archive.seal(MementoRecord(1, "user", b"cannot downgrade"), previous=before)
        with pytest.raises(SealedContextBoundaryError, match="legacy custody"):
            await db.publish(
                archive=archive, expected_head=before, expected_thread_version=3,
                stream="user", ciphertext=wire,
            )

    asyncio.run(scenario())
    assert not owner.database.rows["conversation_memento_frames"]
    assert "_sealed_memento_head" not in owner.database.rows["conversation_threads"]["t1"]


def test_protected_memento_publish_replay_and_erasure_participate_in_actor_epoch(suite, monkeypatch):
    """Witnessed frame transactions and tombstones share actor writer custody."""
    from skeleton.persistence.mongo_source_epoch import (
        MongoCanonicalSourceEpoch, MongoSourceEpochError,
    )
    from skeleton.persistence.sealed_memento_witness import (
        WitnessedMongoMementoAuthority, WitnessPosition, _binding_digest,
    )
    from skeleton.testing.test_mongo_source_epoch import Database
    import pymongo

    monkeypatch.setattr(
        pymongo, "ReturnDocument", SimpleNamespace(AFTER="after"),
        raising=False,
    )
    conversation, mongo, archive, _ = suite
    writer_epoch = MongoCanonicalSourceEpoch(Database())
    conversation.canonical_source_epoch = writer_epoch
    scope = _binding_digest(archive)

    class Witness:
        def __init__(self):
            self.position = WitnessPosition(scope, 1, MementoCatalogHead())

        async def read(self, *, binding_digest):
            assert binding_digest == scope
            return self.position

        async def compare_and_set(self, *, binding_digest, previous, successor):
            if binding_digest != scope or previous != self.position:
                return False
            self.position = successor
            return True

    witness = Witness()
    conversation.memento_witness = witness
    guarded = WitnessedMongoMementoAuthority(mongo, witness=witness)

    async def scenario():
        previous = MementoCatalogHead()
        wire, expected = archive.seal(
            MementoRecord(1, "user", b"initial"), previous=previous,
        )
        with pytest.raises(MongoSourceEpochError, match="writer epoch not owned"):
            await guarded.publish(
                archive=archive, expected_head=previous,
                expected_thread_version=3, stream="user", ciphertext=wire,
            )
        assert conversation.storage_calls == 0
        await writer_epoch.provision_migration_epoch(
            tenant_id="tenant", actor_id="owner",
        )
        published = await guarded.publish(
            archive=archive, expected_head=previous,
            expected_thread_version=3, stream="user", ciphertext=wire,
        )
        assert published == expected
        assert await writer_epoch.read_epoch(
            tenant_id="tenant", actor_id="owner", context_id="t1",
        ) == 4
        page = await guarded.read_window(archive=archive)
        assert [record.payload for record in page.records] == [b"initial"]
        deleted = await guarded.retire_thread(archive=archive)
        assert deleted == 1
        assert witness.position.retired
        assert await writer_epoch.read_epoch(
            tenant_id="tenant", actor_id="owner", context_id="t1",
        ) == 6
        with pytest.raises(SealedContextBoundaryError, match="retired"):
            await mongo.trusted_head(archive=archive)

    asyncio.run(scenario())


def test_witnessed_memento_purge_requires_independent_retirement_tombstone(suite):
    """Raw Mongo erasure cannot bypass the independent witness CAS boundary."""
    from skeleton.persistence.sealed_memento_witness import (
        WitnessPosition, _binding_digest,
    )

    owner, mongo, archive, _ = suite
    scope = _binding_digest(archive)

    async def scenario():
        genesis = MementoCatalogHead()
        wire, head = archive.seal(
            MementoRecord(1, "user", b"confidential"), previous=genesis,
        )
        assert await mongo.publish(
            archive=archive, expected_head=genesis, expected_thread_version=3,
            stream="user", ciphertext=wire, custody_mode="witnessed",
        ) == head

        with pytest.raises(MongoMementoUnavailable, match="independent retirement"):
            await mongo.retire_thread(
                tenant_id="tenant", owner_id="owner", thread_id="t1",
            )
        assert len(owner.database.rows["conversation_memento_frames"]) == 1

        class Witness:
            retired = False

            async def read(self, *, binding_digest):
                assert binding_digest == scope
                return WitnessPosition(scope, 2, head, retired=self.retired)

        witness = Witness()
        owner.memento_witness = witness
        with pytest.raises(MongoMementoUnavailable, match="tombstone not acknowledged"):
            await mongo.retire_thread(
                tenant_id="tenant", owner_id="owner", thread_id="t1",
            )
        assert len(owner.database.rows["conversation_memento_frames"]) == 1

        witness.retired = True
        assert await mongo.retire_thread(
            tenant_id="tenant", owner_id="owner", thread_id="t1",
        ) == 1
        assert not owner.database.rows["conversation_memento_frames"]
        with pytest.raises(SealedContextBoundaryError, match="retired"):
            await mongo.trusted_head(archive=archive)

    asyncio.run(scenario())
