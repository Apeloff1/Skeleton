"""Encrypted Academy checkpoint fidelity, CAS, isolation and tamper tests."""
import sqlite3

import pytest

from skeleton.learning.school.checkpoint_codec import AcademyState, decode_state, encode_state
from skeleton.learning.school.checkpoint_store import (
    AcademyCapacity, AcademyCheckpointStore, AcademyConflict, AcademyIntegrityError,
)
from skeleton.learning.school.decision_ledger import EvidenceKind, EvidenceRef, DecisionDisposition
from skeleton.learning.school.memory import LearnerMemory, MemoryKind
from skeleton.learning.school.reflection import ReflectionEntry, ReflectionKind
from skeleton.learning.school.student import StudentProfile


def open_store(path, owner="tenant", **kwargs):
    db = sqlite3.connect(path)
    return db, AcademyCheckpointStore(db, owner=owner, key=b"a" * 32, **kwargs)


def state():
    result = AcademyState(StudentProfile("learner", "Private learner"))
    result.student.record_evidence("python", .9, evidence="private explanation")
    result.memory.remember(LearnerMemory("memory", "private teaching history", MemoryKind.PROCEDURAL,
                                         skill_ids=("python",)))
    result.reflections.record(ReflectionEntry("reflection", ReflectionKind.SUCCESS,
                                               "Private title", "Private reflection"))
    result.calibrator.observe("practice", reward=.8, successful=True)
    result.ledger.register_evidence(EvidenceRef("evidence", EvidenceKind.ASSESSMENT,
                                               "python", "private evidence", .9))
    result.ledger.append(session_id="session", decision_id="decision", domain="school",
                         action="practice", rationale=("practice chosen",), evidence=("evidence",),
                         disposition=DecisionDisposition.ACCEPTED)
    return result


def test_codec_preserves_learner_memory_and_ledger():
    original = state()
    raw = encode_state(original)
    recovered = decode_state(raw)
    assert recovered.student == original.student
    assert recovered.memory.memories == original.memory.memories
    assert recovered.reflections.entries == original.reflections.entries
    assert recovered.calibrator.snapshot() == original.calibrator.snapshot()
    assert recovered.ledger.ledger_identity == original.ledger.ledger_identity
    assert encode_state(recovered) == raw
    recovered.student.goals.append("new")
    assert original.student.goals == []


def test_versioned_checkpoint_survives_restart_without_plaintext(tmp_path):
    path = tmp_path / "academy.sqlite"
    db, store = open_store(path)
    assert store.load("learner") is None
    original = state()
    first = store.save(original, expected_revision=0, request_id="first")
    assert store.save(original, expected_revision=0, request_id="first") == first
    original.student.goals.append("new skill")
    second = store.save(original, expected_revision=1, request_id="second", trusted_head=first)
    assert second.previous == first.receipt_digest
    with pytest.raises(AcademyConflict):
        store.save(original, expected_revision=0, request_id="wrong")
    store.close()
    db.close()
    assert b"private teaching history" not in path.read_bytes()
    assert b"Private learner" not in path.read_bytes()
    db, restored = open_store(path)
    assert restored.load("learner", trusted_head=second).state.student.goals == ["new skill"]
    assert restored.load_revision("learner", 1, trusted_head=second).state.student.goals == []
    assert restored.history("learner") == (first, second)
    with pytest.raises(AcademyConflict):
        restored.load("learner", trusted_head=first)
    db.close()


def test_account_partition_and_wrong_key_never_restore_other_learner(tmp_path):
    path = tmp_path / "academy.sqlite"
    db, store = open_store(path)
    store.save(state(), expected_revision=0, request_id="first")
    other_db, other = open_store(path, owner="another")
    assert other.load("learner") is None
    assert store.load("another") is None
    other_db.close()
    db.close()


def test_ciphertext_and_tail_tampering_fail_closed(tmp_path):
    db, store = open_store(tmp_path / "academy.sqlite")
    original = state()
    first = store.save(original, expected_revision=0, request_id="one")
    original.student.goals.append("second")
    second = store.save(original, expected_revision=1, request_id="two")
    db.execute("DELETE FROM academy_checkpoint_v1 WHERE revision=2")
    db.commit()
    with pytest.raises(AcademyConflict):
        store.load("learner", trusted_head=second)
    assert store.load("learner").receipt == first
    db.execute("UPDATE academy_checkpoint_v1 SET ciphertext=zeroblob(length(ciphertext))")
    db.commit()
    with pytest.raises(AcademyIntegrityError):
        store.load("learner")
    db.close()


def test_capacity_and_request_conflict_are_atomic(tmp_path):
    db, store = open_store(tmp_path / "academy.sqlite", max_revisions=1)
    original = state()
    first = store.save(original, expected_revision=0, request_id="one")
    original.student.goals.append("changed")
    with pytest.raises(AcademyConflict):
        store.save(original, expected_revision=0, request_id="one")
    with pytest.raises(AcademyCapacity):
        store.save(original, expected_revision=1, request_id="two")
    assert store.history("learner") == (first,)
    db.close()
