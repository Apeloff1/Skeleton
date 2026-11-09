"""Session-scoped evidence commitments and strict recovery tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptState,
)
from skeleton.shells.ai.recovery import RecoveryAction
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.session_journal import SessionJournalEvidence
from skeleton.shells.ai.session_evidence import (
    SessionEvidenceConflict,
    SessionEvidenceStore,
    SessionExecutionEvidence,
    SessionReceiptEvidence,
)
from skeleton.shells.ai.strict_recovery import StrictAIRecoveryManager
from skeleton.shells.dispatch import DispatchResult
from skeleton.shells.durable_receipts import DistributedReceiptChain
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ExecutionOutcome
from skeleton.shells.plan_executor import (
    PlanExecutionReport,
    StepExecution,
    StepState,
)
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.runner import ShellResult


def fp(char):
    return char * 64


def receipt(receipt_id="r", *, correlation="c", fingerprint=None):
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation,
        fingerprint=fingerprint or fp("f"),
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=2,
        stderr_bytes=0,
        receipt_id=receipt_id,
    )


def report(*, with_dispatch=True, receipt_id="r"):
    if with_dispatch:
        item_receipt = receipt(receipt_id)
        result = ShellResult(
            "python",
            0,
            b"ok",
            b"",
            accepted=True,
        )
        outcome = ExecutionOutcome(
            result,
            (item_receipt,),
            "corr",
        )
        dispatch = DispatchResult(
            outcome,
            ExecutionContext("corr"),
            1,
            "lease",
            1.0,
        )
    else:
        dispatch = None
    step = StepExecution(
        "step",
        StepState.SUCCEEDED,
        dispatch,
        "",
        1.0,
        2.0,
    )
    return PlanExecutionReport(
        "plan",
        fp("p"),
        (step,),
        1.0,
        2.0,
    )


def checkpoint(
    *,
    phase="review",
    journal_root=None,
    receipt_root=None,
):
    return AISessionCheckpoint(
        1,
        "session",
        phase,
        "intent",
        fp("i"),
        "proposal",
        fp("p"),
        3,
        journal_root or fp("j"),
        receipt_root or fp("r"),
        fp("q"),
        fp("t"),
        fp("e"),
    )


def test_session_evidence_from_report_with_receipt():
    evidence = SessionExecutionEvidence.from_report(
        "session",
        report(),
    )
    assert evidence.session_id == "session"
    assert evidence.plan_id == "plan"
    assert evidence.plan_fingerprint == fp("p")
    assert evidence.report_ok
    assert evidence.steps[0].receipt_ids == ("r",)
    assert evidence.steps[0].receipt_fingerprints == (fp("f"),)
    assert evidence.steps[0].returncodes == (0,)
    assert evidence.steps[0].attempts == 1
    assert len(evidence.digest) == 64


def test_session_evidence_step_without_dispatch_is_explicit():
    evidence = SessionExecutionEvidence.from_report(
        "session",
        report(with_dispatch=False),
    )
    step = evidence.steps[0]
    assert step.correlation_id == ""
    assert step.receipt_ids == ()
    assert step.attempts == 0
    assert step.ok


def test_session_receipt_vector_lengths_must_match():
    with pytest.raises(ValueError, match="vectors"):
        SessionReceiptEvidence(
            "step",
            "c",
            ("r",),
            (),
            (0,),
            1,
            True,
        )


def test_session_evidence_duplicate_step_rejected():
    step = SessionReceiptEvidence(
        "step",
        "",
        (),
        (),
        (),
        0,
        True,
    )
    with pytest.raises(ValueError, match="duplicate"):
        SessionExecutionEvidence(
            1,
            "session",
            "plan",
            fp("p"),
            True,
            (step, step),
        )


def test_session_evidence_store_create():
    store = SessionEvidenceStore(InMemoryFencedStore())
    evidence = SessionExecutionEvidence.from_report("session", report())
    stored = store.put(evidence)
    assert stored.revision == 1
    assert stored.evidence == evidence
    assert store.current("session") == stored


def test_session_evidence_identical_put_is_idempotent():
    store = SessionEvidenceStore(InMemoryFencedStore())
    evidence = SessionExecutionEvidence.from_report("session", report())
    first = store.put(evidence)
    second = store.put(evidence)
    assert first.revision == second.revision == 1


def test_session_evidence_update_requires_revision_when_given():
    store = SessionEvidenceStore(InMemoryFencedStore())
    first = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="one"),
    )
    second = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="two"),
    )
    store.put(first)
    updated = store.put(second, expected_revision=1)
    assert updated.revision == 2
    assert updated.evidence.digest == second.digest


def test_session_evidence_stale_revision_conflict():
    store = SessionEvidenceStore(InMemoryFencedStore())
    first = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="one"),
    )
    second = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="two"),
    )
    third = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="three"),
    )
    store.put(first)
    store.put(second, expected_revision=1)
    with pytest.raises(SessionEvidenceConflict):
        store.put(third, expected_revision=1)


class BrokenBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        raise OSError("storage down")


def test_session_evidence_backend_outage_propagates():
    backend = BrokenBackend()
    store = SessionEvidenceStore(backend)
    first = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="one"),
    )
    second = SessionExecutionEvidence.from_report(
        "session",
        report(receipt_id="two"),
    )
    store.put(first)
    with pytest.raises(OSError, match="storage down"):
        store.put(second)


def recovery_environment(phase="review", *, session_evidence_digest=""):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    journal.append(
        "review",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    evidence_store = SessionEvidenceStore(
        backend,
        namespace="session-evidence",
    )
    base = checkpoint(
        phase=phase,
        journal_root=journal.root_hash(),
        receipt_root=receipts.root_hash(),
    )
    recovery = AIRecoveryCheckpoint.wrap(
        base,
        session_evidence_digest=session_evidence_digest,
        session_journal_digest=SessionJournalEvidence.from_journal(
            journal,
            "session",
        ).digest,
        release_evidence_digest=fp("l"),
        sandbox_binding_digest=fp("s"),
        runtime_trust_digest=fp("u"),
        authority_health_policy_digest=fp("h"),
    )
    return backend, journal, receipts, evidence_store, recovery


def inspect(manager, recovery, journal, receipts, evidence_store, **changes):
    values = dict(
        current_policy_fingerprint=fp("q"),
        current_tool_catalog_digest=fp("t"),
        current_effect_digest=fp("e"),
        current_release_evidence_digest=fp("l"),
        current_sandbox_binding_digest=fp("s"),
        current_runtime_trust_digest=fp("u"),
        current_authority_health_policy_digest=fp("h"),
    )
    values.update(changes)
    return manager.inspect(
        recovery,
        journal,
        receipts,
        evidence_store,
        **values,
    )


def test_strict_recovery_review_can_resume_with_matching_evidence():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.RESUME_REVIEW
    assert result.safe_to_resume
    assert result.journal_root_matches
    assert result.global_receipt_chain_valid


def test_strict_recovery_global_receipt_advance_unrelated_does_not_force_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    receipts.append(receipt("unrelated", correlation="other"))
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.RESUME_REVIEW
    assert result.global_receipt_chain_valid


def test_strict_recovery_journal_root_advance_requires_manual_review():
    _, journal, receipts, store, recovery = recovery_environment("review")
    journal.append(
        "unexpected",
        session_id="session",
        intent_id="intent",
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.journal_root_matches


def test_strict_recovery_release_drift_requires_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_release_evidence_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert not result.release_evidence_matches


def test_strict_recovery_sandbox_drift_requires_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_sandbox_binding_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert not result.sandbox_binding_matches


def test_strict_recovery_policy_drift_requires_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_policy_fingerprint=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN


def test_strict_recovery_executing_missing_session_evidence_requires_verification():
    _, journal, receipts, store, recovery = recovery_environment(
        "executing",
        session_evidence_digest=fp("x"),
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert not result.session_evidence_matches


def test_strict_recovery_matching_session_evidence_can_preserve_base_action():
    evidence = SessionExecutionEvidence.from_report(
        "session",
        report(),
    )
    _, journal, receipts, store, recovery = recovery_environment(
        "review",
        session_evidence_digest=evidence.digest,
    )
    store.put(evidence)
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.RESUME_REVIEW
    assert result.session_evidence_matches


def test_recovery_checkpoint_digest_changes_with_release():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        release_evidence_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        release_evidence_digest=fp("b"),
    )
    assert first.digest != second.digest


def test_recovery_checkpoint_digest_changes_with_session_evidence():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        session_evidence_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        session_evidence_digest=fp("b"),
    )
    assert first.digest != second.digest


def test_recovery_checkpoint_rejects_invalid_digest():
    with pytest.raises(ValueError):
        AIRecoveryCheckpoint.wrap(
            checkpoint(),
            session_evidence_digest="bad",
        )


def test_strict_recovery_unrelated_global_journal_advance_is_tolerated():
    _, journal, receipts, store, recovery = recovery_environment("review")
    journal.append(
        "other-session-event",
        session_id="other-session",
        intent_id="other-intent",
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.RESUME_REVIEW
    assert not result.journal_root_matches
    assert result.session_journal_matches


def test_strict_recovery_same_session_journal_advance_requires_manual_review():
    _, journal, receipts, store, recovery = recovery_environment("review")
    journal.append(
        "same-session-event",
        session_id="session",
        intent_id="intent",
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.session_journal_matches


def test_recovery_checkpoint_digest_changes_with_session_journal():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        session_journal_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        session_journal_digest=fp("b"),
    )
    assert first.digest != second.digest


def test_strict_recovery_runtime_trust_drift_requires_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_runtime_trust_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert not result.runtime_trust_matches
    assert result.authority_health_policy_matches
    assert any("runtime trust" in reason for reason in result.reasons)


def test_strict_recovery_authority_health_policy_drift_requires_replan():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_authority_health_policy_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert result.runtime_trust_matches
    assert not result.authority_health_policy_matches
    assert any("authority health" in reason for reason in result.reasons)


def test_strict_recovery_matching_trust_and_health_preserve_resume():
    _, journal, receipts, store, recovery = recovery_environment("review")
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.RESUME_REVIEW
    assert result.runtime_trust_matches
    assert result.authority_health_policy_matches


def test_recovery_checkpoint_digest_changes_with_runtime_trust():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        runtime_trust_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        runtime_trust_digest=fp("b"),
    )
    assert first.digest != second.digest


def test_recovery_checkpoint_digest_changes_with_authority_health_policy():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        authority_health_policy_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        authority_health_policy_digest=fp("b"),
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "field",
    [
        "runtime_trust_digest",
        "authority_health_policy_digest",
    ],
)
def test_recovery_checkpoint_rejects_invalid_new_digest(field):
    with pytest.raises(ValueError):
        AIRecoveryCheckpoint.wrap(
            checkpoint(),
            **{field: "bad"},
        )


def test_strict_recovery_integrity_failure_dominates_trust_drift():
    _, journal, receipts, store, recovery = recovery_environment("review")

    class CorruptJournal:
        def verify(self):
            return False

        def root_hash(self):
            return journal.root_hash()

        def snapshot(self):
            return journal.snapshot()

    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        CorruptJournal(),
        receipts,
        store,
        current_runtime_trust_digest=fp("x"),
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.runtime_trust_matches
    assert any("integrity" in reason for reason in result.reasons)


def test_strict_recovery_execution_evidence_drift_keeps_verification_precedence():
    evidence = SessionExecutionEvidence.from_report(
        "session",
        report(),
    )
    _, journal, receipts, store, recovery = recovery_environment(
        "executing",
        session_evidence_digest=evidence.digest,
    )
    # No evidence is stored, and trust also drifted. The interrupted execution
    # must still be verified rather than blindly replanned because side effects
    # may already have occurred.
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        current_runtime_trust_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert not result.session_evidence_matches
    assert not result.runtime_trust_matches


def _attempt_checkpoint(
    recovery,
    attempts,
    *,
    state=ExecutionAttemptState.AUTHORIZED,
):
    stored = attempts.reserve(
        attempt_id="seal-attempt",
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-attempt",
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
        execution_backend_id="shell-service-host",
    )
    attempt = stored.attempt
    if state is ExecutionAttemptState.BOUNDARY_ENTERED:
        attempt = attempts.enter_boundary(attempt).attempt
    elif state is ExecutionAttemptState.SUCCEEDED:
        attempt = attempts.enter_boundary(attempt).attempt
        attempt = attempts.succeed(
            attempt,
            terminal_evidence_digest=fp("z"),
        ).attempt
    elif state is ExecutionAttemptState.FAILED:
        attempt = attempts.enter_boundary(attempt).attempt
        attempt = attempts.fail(
            attempt,
            error_type="RuntimeError",
        ).attempt
    elif state is ExecutionAttemptState.ABANDONED:
        attempt = attempts.abandon(attempt).attempt
    return replace(
        recovery,
        execution_attempt_id=attempt.attempt_id,
        execution_attempt_authority_digest=attempt.authority_digest,
    ), attempt


def test_recovery_checkpoint_digest_changes_with_execution_attempt_binding():
    base = checkpoint()
    first = AIRecoveryCheckpoint.wrap(
        base,
        execution_attempt_id="attempt-a",
        execution_attempt_authority_digest=fp("a"),
    )
    second = AIRecoveryCheckpoint.wrap(
        base,
        execution_attempt_id="attempt-b",
        execution_attempt_authority_digest=fp("b"),
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "attempt_id,authority_digest",
    [
        ("attempt", ""),
        ("", fp("a")),
        ("x" * 257, fp("a")),
        ("attempt", "bad"),
    ],
)
def test_recovery_checkpoint_validates_execution_attempt_binding(
    attempt_id,
    authority_digest,
):
    with pytest.raises(ValueError):
        AIRecoveryCheckpoint.wrap(
            checkpoint(),
            execution_attempt_id=attempt_id,
            execution_attempt_authority_digest=authority_digest,
        )


def test_strict_recovery_authorized_attempt_requires_replan():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, attempt = _attempt_checkpoint(recovery, attempts)
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert result.execution_attempt_matches
    assert result.execution_attempt_recovery == "not_started"
    assert any("process boundary was not entered" in reason for reason in result.reasons)


def test_strict_recovery_boundary_entered_requires_verification():
    backend, journal, receipts, store, recovery = recovery_environment("executing")
    attempts = AIExecutionAttemptStore(backend)
    recovery, attempt = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.BOUNDARY_ENTERED,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert result.execution_attempt_matches
    assert result.execution_attempt_recovery == "require_verification"
    assert any("crossed process boundary" in reason for reason in result.reasons)


def test_strict_recovery_boundary_ambiguity_dominates_runtime_replan():
    backend, journal, receipts, store, recovery = recovery_environment("executing")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.BOUNDARY_ENTERED,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
        current_runtime_trust_digest=fp("x"),
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert not result.runtime_trust_matches


def test_strict_recovery_failed_attempt_without_terminal_evidence_requires_verification():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.FAILED,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert result.execution_attempt_recovery == "terminal_failure"
    assert any(
        "without terminal evidence" in reason
        for reason in result.reasons
    )


def test_strict_recovery_failed_attempt_with_terminal_evidence_marks_failed():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    stored = attempts.reserve(
        attempt_id="seal-failed-evidence",
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-failed-evidence",
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("l"),
        execution_backend_id="shell-service-host",
    )
    attempt = attempts.enter_boundary(stored.attempt).attempt
    attempt = attempts.fail(
        attempt,
        error_type="ExecutionOrVerificationFailed",
        terminal_evidence_digest=fp("z"),
    ).attempt
    recovery = replace(
        recovery,
        execution_attempt_id=attempt.attempt_id,
        execution_attempt_authority_digest=attempt.authority_digest,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.MARK_FAILED
    assert result.execution_attempt_recovery == "terminal_failure"
    assert any(
        "terminal failure with terminal evidence" in reason
        for reason in result.reasons
    )


def test_strict_recovery_abandoned_attempt_requires_replan():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.ABANDONED,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.REQUIRE_REPLAN
    assert result.execution_attempt_recovery == "abandoned"


def test_strict_recovery_missing_attempt_store_is_manual_review():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(recovery, attempts)
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.execution_attempt_matches


def test_strict_recovery_missing_attempt_record_is_manual_review():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, attempt = _attempt_checkpoint(recovery, attempts)
    empty_attempts = AIExecutionAttemptStore(
        InMemoryFencedStore(),
        namespace=attempts.namespace,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=empty_attempts,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.execution_attempt_matches


def test_strict_recovery_attempt_authority_tamper_is_manual_review():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(recovery, attempts)
    recovery = replace(
        recovery,
        execution_attempt_authority_digest=fp("x"),
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert not result.execution_attempt_matches


def test_strict_recovery_integrity_failure_dominates_attempt_state():
    backend, journal, receipts, store, recovery = recovery_environment("executing")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.BOUNDARY_ENTERED,
    )

    class CorruptJournal:
        def verify(self):
            return False

        def root_hash(self):
            return journal.root_hash()

        def snapshot(self):
            return journal.snapshot()

    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        CorruptJournal(),
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
    assert result.execution_attempt_recovery == "require_verification"


def test_strict_recovery_report_exposes_attempt_evidence_fields():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(recovery, attempts)
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    data = result.to_dict()
    assert data["execution_attempt_matches"] is True
    assert data["execution_attempt_recovery"] == "not_started"


def test_strict_recovery_terminal_success_newer_than_review_checkpoint_requires_verification():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, attempt = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.SUCCEEDED,
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.REQUIRE_VERIFICATION
    assert result.execution_attempt_matches
    assert result.execution_attempt_recovery == "terminal_success"
    assert any("newer than" in reason for reason in result.reasons)


def test_strict_recovery_terminal_success_authority_tamper_is_manual_review():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.SUCCEEDED,
    )
    recovery = replace(
        recovery,
        execution_attempt_authority_digest=fp("x"),
    )
    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        receipts,
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW


def test_strict_recovery_attempt_state_cannot_weaken_integrity_failure():
    backend, journal, receipts, store, recovery = recovery_environment("review")
    attempts = AIExecutionAttemptStore(backend)
    recovery, _ = _attempt_checkpoint(
        recovery,
        attempts,
        state=ExecutionAttemptState.SUCCEEDED,
    )

    class CorruptReceipts:
        def verify(self):
            return False

    result = inspect(
        StrictAIRecoveryManager(),
        recovery,
        journal,
        CorruptReceipts(),
        store,
        execution_attempts=attempts,
    )
    assert result.action is RecoveryAction.MANUAL_REVIEW
