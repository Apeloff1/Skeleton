"""Simulated operator recovery: no backend retry or GPU/device qualification."""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_recovery import (
    RecoveryAuthorizationDenied, issue_recovery_authorization,
    verify_recovery_authorization,
)
from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    ExecutionOutcomeUnknown, FairStreamExecutionJournal,
    JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase
from skeleton.app.offline_dispatch_bridge import OfflineAdaptiveDispatchService

CUSTODY_KEY = b"c" * 32
EXECUTION_KEY = b"e" * 32
RECOVERY_KEY = b"r" * 32
SESSION = "a" * 32


class Anchor:
    """Deterministic test double, NOT an independently durable high-watermark."""

    def __init__(self):
        self.value = None

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("already initialized")
        self.value = generation, digest

    def read(self):
        if self.value is None:
            raise ValueError("uninitialized")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.value != (expected_generation, expected_digest):
            raise ValueError("stale anchor")
        self.value = generation, digest


class Backend:
    def __init__(self):
        self.calls = 0

    def run_and_commit(self, permit, state):
        self.calls += 1
        return permit.tokens, "d" * 64


class CrashAfterJournalCommit:
    """Simulate a lost response after a durable signed journal commit."""

    def __init__(self, journal, backend):
        self.owner = JournaledExecutionOwner(journal, backend)

    def execute_and_commit(self, permit, state):
        self.owner.execute_and_commit(permit, state)
        raise OSError("lost response after committed execution")


def sample(self, *, token_budget, storage_path):
    return (
        MeasuredStreamBudget(4096, 1024, token_budget, 1, 0, False, "os_probe"),
        {
            "measurement": "os_probe",
            "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        },
    )


def make(connection, anchor, owner, *, bootstrap):
    return OfflineAdaptiveDispatchService.from_trusted_handles(
        connection=connection, custody_key=CUSTODY_KEY,
        execution_key=EXECUTION_KEY, session_id=SESSION,
        watermark=anchor, owner=owner, storage_path=".",
        bootstrap=bootstrap,
    )


def setup_pending(monkeypatch, tmp_path):
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    anchor = Anchor()
    custody_path = tmp_path / "custody.db"
    journal_path = tmp_path / "journal.db"
    custody_connection = sqlite3.connect(custody_path)
    journal_connection = sqlite3.connect(journal_path)
    journal = FairStreamExecutionJournal(
        journal_connection, session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    backend = Backend()
    app = make(
        custody_connection, anchor, CrashAfterJournalCommit(journal, backend),
        bootstrap=True,
    )
    app.submit(StreamRequest(
        "request-1", "tenant-1", InferencePhase.PREFILL, 12, 4,
    ))
    with pytest.raises(DispatchUncertain, match="do not re-execute"):
        app.execute_next(token_budget=12)
    assert backend.calls == 1
    assert app.status().pending_leases == 1
    custody_connection.close()
    journal_connection.close()
    resumed_journal = FairStreamExecutionJournal(
        sqlite3.connect(journal_path), session_id=SESSION,
        execution_key=EXECUTION_KEY,
    )
    resumed_app = make(
        sqlite3.connect(custody_path), anchor,
        CrashAfterJournalCommit(resumed_journal, backend), bootstrap=False,
    )
    return resumed_app, resumed_journal, backend, anchor


def grant(app, *, key=RECOVERY_KEY, nonce="f" * 32):
    state = app._session.verify()
    pending = state["checkpoint"]["pending"]
    assert len(pending) == 1
    return issue_recovery_authorization(
        recovery_key=key, session_id=state["session_id"],
        generation=state["generation"],
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=pending[0]["lease_id"], nonce=nonce,
    )


def test_committed_receipt_recovery_after_process_restart(monkeypatch, tmp_path):
    app, journal, backend, anchor = setup_pending(monkeypatch, tmp_path)
    approval = grant(app)
    with pytest.raises(DispatchUncertain, match="pending"):
        app.execute_next(token_budget=12)
    status = app.reconcile_committed(
        journal=journal, authorization=approval, recovery_key=RECOVERY_KEY,
    )
    assert status.pending_leases == 0
    assert not status.execution_uncertain
    assert status.generation == 3
    assert backend.calls == 1
    with pytest.raises(DispatchUncertain, match="pending"):
        app.reconcile_committed(
            journal=journal, authorization=approval, recovery_key=RECOVERY_KEY,
        )
    assert backend.calls == 1


def test_wrong_operator_key_does_not_retire_pending_lease(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    with pytest.raises(RecoveryAuthorizationDenied, match="authentication"):
        app.reconcile_committed(
            journal=journal, authorization=grant(app),
            recovery_key=b"x" * 32,
        )
    assert app.status().pending_leases == 1
    assert backend.calls == 1


def test_cross_session_grant_cannot_retire_lease(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    approval = replace(grant(app), session_id="b" * 32)
    with pytest.raises(RecoveryAuthorizationDenied, match="bind"):
        app.reconcile_committed(
            journal=journal, authorization=approval,
            recovery_key=RECOVERY_KEY,
        )
    assert app.status().pending_leases == 1
    assert backend.calls == 1


def test_invalid_operator_nonce_and_bool_generation_rejected(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    with pytest.raises(RecoveryAuthorizationDenied, match="nonce"):
        grant(app, nonce="not-a-hex-nonce")
    with pytest.raises(RecoveryAuthorizationDenied, match="generation"):
        issue_recovery_authorization(
            recovery_key=RECOVERY_KEY, session_id=SESSION,
            generation=True, checkpoint_digest="b" * 64,
            lease_id="c" * 64, nonce="f" * 32,
        )
    assert app.status().pending_leases == 1
    assert backend.calls == 1


def test_running_intent_never_authorizes_recovery(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    # Simulate a journal where a durable completion receipt never existed.
    journal._connection.execute(
        "UPDATE local_fair_stream_execution_journal "
        "SET state = 'running', consumed_tokens = NULL, "
        "result_digest = NULL, receipt = NULL"
    )
    journal._connection.commit()
    with pytest.raises(DispatchUncertain, match="committed"):
        app.reconcile_committed(
            journal=journal, authorization=grant(app),
            recovery_key=RECOVERY_KEY,
        )
    assert app.status().pending_leases == 1
    assert backend.calls == 1


def test_forged_journal_receipt_fails_closed(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    journal._connection.execute(
        "UPDATE local_fair_stream_execution_journal SET receipt = ?",
        (b'{"forged":true}',),
    )
    journal._connection.commit()
    with pytest.raises(DispatchUncertain, match="committed"):
        app.reconcile_committed(
            journal=journal, authorization=grant(app),
            recovery_key=RECOVERY_KEY,
        )
    assert app.status().pending_leases == 1
    assert backend.calls == 1


def test_rollback_anchor_mismatch_quarantines_recovery(monkeypatch, tmp_path):
    app, journal, backend, anchor = setup_pending(monkeypatch, tmp_path)
    anchor.value = (0, "0" * 64)
    with pytest.raises(Exception):
        app.reconcile_committed(
            journal=journal, authorization=grant(app),
            recovery_key=RECOVERY_KEY,
        )
    assert backend.calls == 1


def test_recovery_key_and_grant_never_enter_public_status(monkeypatch, tmp_path):
    app, journal, backend, _ = setup_pending(monkeypatch, tmp_path)
    status = app.reconcile_committed(
        journal=journal, authorization=grant(app),
        recovery_key=RECOVERY_KEY,
    )
    assert set(status.__dataclass_fields__) == {
        "schema", "generation", "pending_leases",
        "quarantined", "execution_uncertain",
    }
    assert RECOVERY_KEY.hex() not in repr(status)
    assert backend.calls == 1
