"""Deterministic durable execution intent and signed recovery regressions."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    ExecutionOutcomeUnknown, FairStreamExecutionJournal,
    JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result

KEY = b"e" * 32
SESSION = "a" * 32
CHECKPOINT = "b" * 64
LEASE = "c" * 64


def permit():
    return DispatchPermit(LEASE, "request-1", 2, CHECKPOINT, 16, 1024)


def state():
    return {
        "session_id": SESSION, "generation": 2,
        "checkpoint_digest": CHECKPOINT,
        "checkpoint": {"pending": [{
            "lease_id": LEASE, "request_id": "request-1",
            "tokens": 16, "bytes_reserved": 1024,
        }]},
    }


def journal(connection=None):
    return FairStreamExecutionJournal(
        connection or sqlite3.connect(":memory:"),
        session_id=SESSION, execution_key=KEY,
    )


class Backend:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def run_and_commit(self, permit, state):
        self.calls += 1
        if self.fail:
            raise OSError("simulated crash after backend may have committed")
        return 8, "d" * 64


def test_commit_and_authenticated_receipt():
    j = journal()
    backend = Backend()
    owner = JournaledExecutionOwner(j, backend)
    receipt = owner.execute_and_commit(permit(), state())
    assert backend.calls == 1
    assert receipt == sign_execution_result(
        execution_key=KEY, session_id=SESSION,
        generation=2, checkpoint_digest=CHECKPOINT,
        lease_id=LEASE, consumed_tokens=8, result_digest="d" * 64,
    )
    assert j.recover_committed_receipt(permit()) == receipt
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        owner.execute_and_commit(permit(), state())
    assert backend.calls == 1


def test_backend_uncertain_outcome_is_not_retried():
    j = journal()
    backend = Backend(fail=True)
    owner = JournaledExecutionOwner(j, backend)
    with pytest.raises(OSError, match="simulated crash"):
        owner.execute_and_commit(permit(), state())
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        owner.execute_and_commit(permit(), state())
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        j.recover_committed_receipt(permit())
    assert backend.calls == 1


def test_restart_retains_running_intent(tmp_path):
    path = tmp_path / "separate-journal.db"
    connection = sqlite3.connect(path)
    first = journal(connection)
    first.begin(permit())
    connection.close()
    second = journal(sqlite3.connect(path))
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        second.begin(permit())
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        second.recover_committed_receipt(permit())


def test_restart_running_request_cannot_replay_with_different_lease(tmp_path):
    path = tmp_path / "separate-journal.db"
    connection = sqlite3.connect(path)
    first = journal(connection)
    first.begin(permit())
    connection.close()
    restarted = journal(sqlite3.connect(path))
    forged_lease = DispatchPermit("f" * 64, "request-1", 3, CHECKPOINT, 16, 1024)
    with pytest.raises(ExecutionOutcomeUnknown, match="request already"):
        restarted.begin(forged_lease)
    assert restarted._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 1


def test_distinct_request_can_begin_after_existing_running_intent():
    j = journal()
    j.begin(permit())
    independent = DispatchPermit("f" * 64, "request-2", 3, CHECKPOINT, 4, 256)
    j.begin(independent)
    assert j._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 2


def test_nonunique_request_replay_index_is_rejected_on_restart(tmp_path):
    path = tmp_path / "separate-journal.db"
    connection = sqlite3.connect(path)
    journal(connection)
    connection.execute("DROP INDEX local_fair_stream_execution_request_identity")
    connection.execute(
        "CREATE INDEX local_fair_stream_execution_request_identity"
        " ON local_fair_stream_execution_journal (session_id, request_id)"
    )
    connection.close()
    with pytest.raises(ValueError, match="request replay index"):
        journal(sqlite3.connect(path))


def test_restart_recovers_committed_receipt_without_execution(tmp_path):
    path = tmp_path / "separate-journal.db"
    connection = sqlite3.connect(path)
    first = journal(connection)
    first.begin(permit())
    receipt = first.commit(
        permit(), consumed_tokens=7, result_digest="d" * 64,
    )
    connection.close()
    second = journal(sqlite3.connect(path))
    assert second.recover_committed_receipt(permit()) == receipt
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        second.begin(permit())


def test_tampered_receipt_rejected():
    connection = sqlite3.connect(":memory:")
    j = journal(connection)
    j.begin(permit())
    j.commit(permit(), consumed_tokens=8, result_digest="d" * 64)
    connection.execute(
        "UPDATE local_fair_stream_execution_journal SET receipt = ?",
        (b'{"forged":true}',),
    )
    connection.commit()
    with pytest.raises(ExecutionOutcomeUnknown, match="authentication"):
        j.recover_committed_receipt(permit())


def test_missing_or_wrong_state_cannot_execute():
    backend = Backend()
    owner = JournaledExecutionOwner(journal(), backend)
    bad = state()
    bad["generation"] = 3
    with pytest.raises(ExecutionOutcomeUnknown, match="bind"):
        owner.execute_and_commit(permit(), bad)
    bad = state()
    bad["checkpoint"]["pending"][0]["tokens"] = 17
    with pytest.raises(ExecutionOutcomeUnknown, match="differs"):
        owner.execute_and_commit(permit(), bad)
    assert backend.calls == 0


def test_commit_requires_running_intent():
    j = journal()
    with pytest.raises(ExecutionOutcomeUnknown, match="missing"):
        j.commit(permit(), consumed_tokens=1, result_digest="d" * 64)


def test_invalid_consumption_does_not_change_running_intent():
    j = journal()
    j.begin(permit())
    with pytest.raises(ValueError, match="consumed"):
        j.commit(permit(), consumed_tokens=17, result_digest="d" * 64)
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        j.recover_committed_receipt(permit())


def test_forged_backend_digest_never_commits():
    class Forged:
        def run_and_commit(self, permit, state):
            return 4, "not-hex"
    j = journal()
    owner = JournaledExecutionOwner(j, Forged())
    with pytest.raises(ValueError, match="result digest"):
        owner.execute_and_commit(permit(), state())
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        j.recover_committed_receipt(permit())


def test_bounded_journal_rows(monkeypatch):
    from skeleton.ai.model_runtime import fair_stream_execution_journal as module
    monkeypatch.setattr(module, "MAX_JOURNAL_ROWS", 1)
    j = journal()
    j.begin(permit())
    second = DispatchPermit("f" * 64, "request-2", 3, "e" * 64, 4, 100)
    with pytest.raises(ExecutionOutcomeUnknown, match="capacity"):
        j.begin(second)


def test_wrong_session_or_lease_never_recovers():
    j = journal()
    j.begin(permit())
    j.commit(permit(), consumed_tokens=1, result_digest="d" * 64)
    different = DispatchPermit("f" * 64, "request-1", 2, CHECKPOINT, 16, 1024)
    with pytest.raises(ExecutionOutcomeUnknown):
        j.recover_committed_receipt(different)


def test_preexisting_wrong_schema_rejected():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE local_fair_stream_execution_journal (lease_id TEXT)"
    )
    with pytest.raises(ValueError, match="schema"):
        journal(connection)

def test_unstarted_cancellation_fences_request_permanently_without_result(tmp_path):
    from dataclasses import replace

    path = tmp_path / "cancelled-intent.db"
    conn = sqlite3.connect(path)
    first = journal(conn)
    receipt = first.fence_unstarted(permit())
    assert receipt["schema"].endswith("unstarted-cancellation.v1")
    assert "result_digest" not in receipt and "consumed_tokens" not in receipt
    conn.close()
    second = journal(sqlite3.connect(path))
    assert second.request_exists(permit().request_id)
    assert second.recover_cancelled_receipt(permit()) == receipt
    with pytest.raises(ExecutionOutcomeUnknown, match="cancellation"):
        second.recover_cancelled_receipt(replace(permit(), generation=3))
    for p in (permit(), replace(permit(), lease_id="f" * 64)):
        with pytest.raises(ExecutionOutcomeUnknown, match="already"):
            second.begin(p)
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        second.recover_committed_receipt(permit())


def test_unstarted_cancellation_refuses_existing_execution_intent():
    j = journal()
    j.begin(permit())
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        j.fence_unstarted(permit())
    assert j._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_cancelled_intents"
    ).fetchone()[0] == 0

def test_cancellation_reader_rejects_conflicting_execution_history():
    j = journal()
    p = permit()
    j.fence_unstarted(p)
    j._connection.execute(
        "INSERT INTO local_fair_stream_execution_journal "
        "(lease_id,session_id,generation,checkpoint_digest,request_id,state) VALUES (?,?,?,?,?,'running')",
        (p.lease_id, SESSION, p.generation, p.checkpoint_digest, p.request_id),
    )
    j._connection.commit()
    with pytest.raises(ExecutionOutcomeUnknown, match="conflicting"):
        j.recover_cancelled_receipt(p)


@pytest.mark.parametrize("table", ["local_fair_stream_execution_journal", "local_fair_stream_cancelled_intents"])
@pytest.mark.parametrize("temporary", [False, True])
def test_late_trigger_cannot_erase_execution_or_cancel_fences(table, temporary):
    from skeleton.ai.model_runtime.sqlite_custody_schema import CustodySchemaError
    j = journal()
    prefix = "CREATE TEMP TRIGGER" if temporary else "CREATE TRIGGER"
    j._connection.execute(
        prefix + " erase_identity AFTER INSERT ON " + table +
        " BEGIN DELETE FROM " + table + "; END"
    )
    with pytest.raises(CustodySchemaError, match="trigger"):
        j.begin(permit())
    with pytest.raises(CustodySchemaError, match="trigger"):
        j.fence_unstarted(permit())
    assert not j._connection.in_transaction
    assert j._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    j._connection.execute("DROP TRIGGER erase_identity")
    j.begin(permit())
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        j.fence_unstarted(permit())


def test_cancel_fence_unique_lease_constraint_required_after_open():
    from skeleton.ai.model_runtime.sqlite_custody_schema import CustodySchemaError
    j = journal()
    j._connection.execute("DROP TABLE local_fair_stream_cancelled_intents")
    j._connection.execute(
        "CREATE TABLE local_fair_stream_cancelled_intents ("
        "session_id TEXT NOT NULL, request_id TEXT NOT NULL, "
        "lease_id TEXT NOT NULL, receipt BLOB NOT NULL,"
        "PRIMARY KEY(session_id,request_id)) WITHOUT ROWID"
    )
    with pytest.raises(CustodySchemaError, match="unique"):
        j.fence_unstarted(permit())
    with pytest.raises(CustodySchemaError, match="unique"):
        j.begin(permit())


def test_late_replay_index_change_blocks_recovery():
    from skeleton.ai.model_runtime.sqlite_custody_schema import CustodySchemaError
    j = journal()
    j.begin(permit())
    j.commit(permit(), consumed_tokens=8, result_digest="d" * 64)
    j._connection.execute("DROP INDEX local_fair_stream_execution_request_identity")
    j._connection.execute(
        "CREATE INDEX local_fair_stream_execution_request_identity "
        "ON local_fair_stream_execution_journal(session_id, request_id)"
    )
    with pytest.raises(CustodySchemaError, match="replay index"):
        j.recover_committed_receipt(permit())
    assert not j._connection.in_transaction


def test_admission_capacity_counts_cancellation_fences(monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_execution_journal as module
    j = journal()
    j.fence_unstarted(permit())
    monkeypatch.setattr(module, "MAX_JOURNAL_ROWS", 2)
    j.assert_request_admissible("other")
    with pytest.raises(ExecutionOutcomeUnknown, match="capacity"):
        j.assert_request_admissible("other", queued_count=1)
    with pytest.raises(ExecutionOutcomeUnknown, match="cancelled"):
        j.assert_request_admissible(permit().request_id)


def test_inherited_execution_owner_refuses_before_lock(monkeypatch):
    import os
    j = journal()
    backend = Backend()
    owner = JournaledExecutionOwner(j, backend)
    class ForbiddenLock:
        def __enter__(self):
            pytest.fail("inherited owner reached process-local lock")
    monkeypatch.setattr(j, "_lock", ForbiddenLock())
    monkeypatch.setattr(owner, "_lock", ForbiddenLock())
    pid = os.getpid()
    with monkeypatch.context() as patch:
        patch.setattr(os, "getpid", lambda: pid + 1)
        with pytest.raises(ExecutionOutcomeUnknown, match="inherited"):
            owner.execute_and_commit(permit(), state())
        with pytest.raises(ExecutionOutcomeUnknown, match="inherited"):
            j.fence_unstarted(permit())
        with pytest.raises(ExecutionOutcomeUnknown, match="inherited"):
            j.request_exists("request-1")
    assert backend.calls == 0

@pytest.mark.parametrize("overrides", [
    {"device_qualified": 0}, {"device_qualified": True},
    {"generation": True}, {"generation": -1}, {"generation": 1 << 63},
    {"tokens": True}, {"tokens": 0}, {"tokens": (1 << 24) + 1},
    {"bytes_reserved": True}, {"bytes_reserved": 0},
    {"bytes_reserved": 1 << 63}, {"request_id": "invalid\x00identity"},
    {"request_id": "\ud800"}, {"request_id": "x" * 129},
    {"lease_id": "X" * 64}, {"checkpoint_digest": "short"},
])
def test_every_journal_boundary_rejects_malformed_permit(overrides):
    from dataclasses import replace

    db = journal()
    bad = replace(permit(), **overrides)
    operations = (
        lambda: db.begin(bad),
        lambda: db.commit(bad, consumed_tokens=1, result_digest="e" * 64),
        lambda: db.fence_unstarted(bad),
        lambda: db.recover_cancelled_receipt(bad),
        lambda: db.require_running_intent(bad),
        lambda: db.recover_committed_receipt(bad),
        lambda: db.record_abandonment(bad, evidence_digest="f" * 64),
    )
    for operation in operations:
        with pytest.raises(ValueError):
            operation()
    assert not db._connection.in_transaction
    for table in ("local_fair_stream_execution_journal", "local_fair_stream_cancelled_intents"):
        assert db._connection.execute("SELECT COUNT(*) FROM " + table).fetchone() == (0,)


def test_owner_rejects_boolean_state_resource_aliases():
    from dataclasses import replace

    db = journal()
    backend = Backend()
    owner = JournaledExecutionOwner(db, backend)
    p = replace(permit(), generation=1, tokens=1, bytes_reserved=1)
    valid = state()
    valid["generation"] = 1
    valid["checkpoint"]["pending"][0].update(tokens=1, bytes_reserved=1)
    for field in ("generation", "tokens", "bytes_reserved"):
        import copy
        bad = copy.deepcopy(valid)
        if field == "generation":
            bad[field] = True
        else:
            bad["checkpoint"]["pending"][0][field] = True
        with pytest.raises(ExecutionOutcomeUnknown):
            owner.execute_and_commit(p, bad)
    assert backend.calls == 0
    assert not db.request_exists(p.request_id)


def test_cancellation_lease_collision_is_rejected_without_creating_second_fence():
    from dataclasses import replace

    db = journal()
    original = permit()
    first = db.fence_unstarted(original)
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        db.fence_unstarted(replace(original, request_id="different"))
    assert db.recover_cancelled_receipt(original) == first
    assert not db.request_exists("different")

def test_batched_admission_uses_one_capacity_snapshot(monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_execution_journal as module

    db = journal()
    db.fence_unstarted(permit())
    monkeypatch.setattr(module, "MAX_JOURNAL_ROWS", 4)
    calls = []
    original = db._capacity
    def capacity(**kwargs):
        calls.append(kwargs["queued_count"])
        return original(**kwargs)
    monkeypatch.setattr(db, "_capacity", capacity)
    db.assert_requests_admissible(("a", "b", "c"))
    assert calls == [2]
    with pytest.raises(ExecutionOutcomeUnknown, match="capacity"):
        db.assert_requests_admissible(("a", "b", "c", "d"))
    with pytest.raises(ExecutionOutcomeUnknown, match="cancelled"):
        db.assert_requests_admissible(("a", permit().request_id))
    for invalid in ((), ("a", "a"), ("a", "bad\x00id"), ("a", 1), ["a"]):
        with pytest.raises(ValueError):
            db.assert_requests_admissible(invalid)
    assert not db._connection.in_transaction
    assert db._connection.execute("SELECT COUNT(*) FROM local_fair_stream_cancelled_intents").fetchone() == (1,)

def test_recursive_owner_cannot_commit_outer_or_create_inner_intent(monkeypatch):
    j = journal()
    backend = Backend()
    owner = JournaledExecutionOwner(j, backend)
    second = DispatchPermit("f" * 64, "second", 3, CHECKPOINT, 16, 1024)
    nested = state()
    nested["generation"] = second.generation
    nested["checkpoint"]["pending"][0].update(
        lease_id=second.lease_id, request_id=second.request_id,
    )

    def recursive(p, s):
        with pytest.raises(ExecutionOutcomeUnknown, match="recursive execution"):
            owner.execute_and_commit(second, nested)
        return 8, "d" * 64

    monkeypatch.setattr(backend, "run_and_commit", recursive)
    with pytest.raises(ExecutionOutcomeUnknown, match="invalidated"):
        owner.execute_and_commit(permit(), state())
    assert j._connection.execute(
        "SELECT lease_id,state FROM local_fair_stream_execution_journal",
    ).fetchall() == [(LEASE, "running")]
    assert not j.request_exists(second.request_id)

def test_oversized_receipt_cannot_alias_running_intent(monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_execution_journal as module

    j = journal()
    p = permit()
    j.begin(p)
    j._connection.execute(
        "UPDATE local_fair_stream_execution_journal SET receipt=zeroblob(8192)",
    )
    j._connection.commit()
    monkeypatch.setattr(module, "MAX_RECEIPT_BYTES", 1024)
    with pytest.raises(ExecutionOutcomeUnknown, match="invalid stored execution receipt"):
        j.require_running_intent(p)
    with pytest.raises(ExecutionOutcomeUnknown, match="invalid stored execution receipt"):
        j.commit(p, consumed_tokens=1, result_digest="d" * 64)
    assert j._connection.execute(
        "SELECT state,length(receipt) FROM local_fair_stream_execution_journal",
    ).fetchone() == ("running", 8192)
    assert not j._connection.in_transaction
