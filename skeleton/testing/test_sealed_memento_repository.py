"""Exact-head SQLite memento publication/replay conformance checks."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.context.sealed_memento import (
    MementoCatalogHead, MementoRecord, SealedMementoArchive, correlate_causal_bundle,
)
from skeleton.context.sealed_sandwich import (
    ContextBinding, ContextSandwichCodec, SealedContextBoundaryError,
    SealedContextReplayError,
)
from skeleton.persistence.conversation_repository import (
    ConversationAuthorizationError, SQLiteConversationRepository,
)
from skeleton.persistence.sealed_memento_repository import (
    MementoAuthorityConflict, SQLiteMementoAuthority,
)


@pytest.fixture
def live(tmp_path):
    repository = SQLiteConversationRepository(tmp_path / "sealed-context.sqlite3")
    thread = repository.create_thread(tenant_id="tenant-a", owner_id="owner-a")
    binding = ContextBinding("tenant-a", "owner-a", thread.thread_id, "model-a", "policy-a")
    approvals = {"artifact:1": hashlib.sha256(b"actual bytes").hexdigest()}

    def verified_work(ref, digest, payload):
        return approvals.get(ref) == digest and hashlib.sha256(payload).hexdigest() == digest

    archive = SealedMementoArchive(
        ContextSandwichCodec({"key-1": b"x" * 32}, active_key_id="key-1"),
        binding, work_verifier=verified_work,
    )
    return repository, SQLiteMementoAuthority(repository), archive, approvals


def publish(db, archive, record, *, expected_version=1):
    before = db.trusted_head(archive=archive)
    ciphertext, after = archive.seal(record, previous=before)
    assert db.publish(
        archive=archive, expected_head=before, expected_thread_version=expected_version,
        stream=record.stream, ciphertext=ciphertext,
    ) == after
    return ciphertext, after


def test_three_correlated_streams_use_one_atomic_trusted_head(live):
    repository, db, archive, _ = live
    publish(db, archive, MementoRecord(1, "user", b"Build something"))
    publish(db, archive, MementoRecord(2, "llm", b"Working on it", causal_serial=1))
    digest = hashlib.sha256(b"actual bytes").hexdigest()
    publish(db, archive, MementoRecord(
        3, "work", b"actual bytes", causal_serial=1,
        evidence_ref="artifact:1", evidence_digest=digest,
    ))
    page = db.read_window(archive=archive)
    assert [record.stream for record in page.records] == ["user", "llm", "work"]
    assert not page.has_more and page.verified_head == db.trusted_head(archive=archive)
    assert [record.serial for record in correlate_causal_bundle(
        page.records, query="Build", serial=1
    )] == [1, 2, 3]
    assert repository._connection.execute(
        "SELECT count(*) FROM conversation_memento_frame"
    ).fetchone()[0] == 3


def test_stale_head_and_stale_thread_version_fail_without_partial_commit(live):
    repository, db, archive, _ = live
    genesis = MementoCatalogHead()
    publish(db, archive, MementoRecord(1, "user", b"one"))
    stale_cipher, _ = archive.seal(MementoRecord(1, "user", b"other"), previous=genesis)
    with pytest.raises(MementoAuthorityConflict):
        db.publish(
            archive=archive, expected_head=genesis, expected_thread_version=1,
            stream="user", ciphertext=stale_cipher,
        )
    head = db.trusted_head(archive=archive)
    wire, _ = archive.seal(MementoRecord(2, "llm", b"two", causal_serial=1), previous=head)
    repository._connection.execute(
        "UPDATE conversation_thread SET version=2 WHERE thread_id=?",
        (archive.binding.conversation_id,),
    )
    with pytest.raises(MementoAuthorityConflict):
        db.publish(
            archive=archive, expected_head=head, expected_thread_version=1,
            stream="llm", ciphertext=wire,
        )
    assert db.trusted_head(archive=archive) == head
    assert len(db.read_window(archive=archive).records) == 1


def test_cross_tenant_and_model_policy_mismatch_denied(live):
    _, db, archive, _ = live
    publish(db, archive, MementoRecord(1, "user", b"confidential"))
    intruder = SealedMementoArchive(
        archive.codec, replace(archive.binding, tenant_id="other")
    )
    with pytest.raises(ConversationAuthorizationError):
        db.read_window(archive=intruder)
    incompatible = SealedMementoArchive(
        archive.codec, replace(archive.binding, model_id="another-model")
    )
    with pytest.raises(SealedContextBoundaryError):
        db.read_window(archive=incompatible)


def test_work_proof_is_checked_again_on_read(live):
    _, db, archive, approvals = live
    digest = hashlib.sha256(b"actual bytes").hexdigest()
    publish(db, archive, MementoRecord(
        1, "work", b"actual bytes", evidence_digest=digest, evidence_ref="artifact:1"
    ))
    approvals.clear()
    with pytest.raises(SealedContextBoundaryError):
        db.read_window(archive=archive)


def test_2000_record_windows_survive_restart(live):
    repository, db, archive, _ = live
    for serial in range(1, 2005):
        publish(db, archive, MementoRecord(serial, "user", str(serial).encode()))
    first = db.read_window(archive=archive)
    second = db.read_window(archive=archive, after_serial=2000)
    assert first.has_more and first.verified_head.serial == 2000
    assert [record.serial for record in second.records] == [2001, 2002, 2003, 2004]
    assert second.starting_head == first.verified_head and not second.has_more
    path = repository._connection.execute("PRAGMA database_list").fetchone()["file"]
    repository.close()
    recovered = SQLiteConversationRepository(path)
    reread = SQLiteMementoAuthority(recovered).read_window(
        archive=archive, after_serial=2000
    )
    assert [record.serial for record in reread.records] == [2001, 2002, 2003, 2004]
    recovered.close()


def test_owner_deletion_cascades_encrypted_history(live):
    repository, db, archive, _ = live
    publish(db, archive, MementoRecord(1, "user", b"delete"))
    repository._connection.execute(
        "DELETE FROM conversation_thread WHERE thread_id=?",
        (archive.binding.conversation_id,),
    )
    assert repository._connection.execute(
        "SELECT count(*) FROM conversation_memento_frame"
    ).fetchone()[0] == 0
    assert repository._connection.execute(
        "SELECT count(*) FROM conversation_memento_head"
    ).fetchone()[0] == 0

def test_pinned_sqlite_cursor_rejects_tampered_saved_checkpoint(live):
    from skeleton.context.sealed_memento import encode_catalog_head
    repository, db, archive, _ = live
    for number in range(1, 4):
        publish(db, archive, MementoRecord(number, "user", str(number).encode()))
    first = db.read_window(archive=archive, limit=1)
    valid = db.read_window(
        archive=archive, after_serial=1, expected_starting_head=first.verified_head,
    )
    assert [r.serial for r in valid.records] == [2, 3]
    replaced = replace(first.verified_head, commitment="a" * 64)
    repository._connection.execute(
        "UPDATE conversation_memento_frame SET head_blob=? WHERE global_serial=1",
        (encode_catalog_head(replaced),),
    )
    with pytest.raises(MementoAuthorityConflict):
        db.read_window(
            archive=archive, after_serial=1, expected_starting_head=first.verified_head,
        )
