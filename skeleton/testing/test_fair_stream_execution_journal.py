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
