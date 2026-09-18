"""Checkpoint-independent durable execution-attempt recovery tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.attempt_recovery import (
    AIExecutionAttemptRecoveryInspector,
    AttemptRecoveryDisposition,
    AttemptRecoveryExpectation,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptSessionHead,
    ExecutionAttemptState,
)


def fp(char: str) -> str:
    return char * 64


def store():
    return AIExecutionAttemptStore(InMemoryFencedStore())


def reserve(target, **changes):
    values = dict(
        attempt_id="seal-1",
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        execution_backend_id="shell-service-host",
    )
    values.update(changes)
    return target.reserve(**values).attempt


def expectation(**changes):
    values = dict(
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        execution_backend_id="shell-service-host",
    )
    values.update(changes)
    return AttemptRecoveryExpectation(**values)


def test_recovery_no_attempt_is_explicit():
    target = store()
    report = AIExecutionAttemptRecoveryInspector(target).inspect("session")
    assert report.disposition is AttemptRecoveryDisposition.NO_ATTEMPT
    assert report.attempt is None
    assert report.attempt_id == ""
    assert report.authority_matches
    assert not report.safe_to_replan
    assert not report.requires_verification


def test_recovery_authorized_attempt_requires_replan():
    target = store()
    reserve(target)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert report.disposition is AttemptRecoveryDisposition.REPLAN
    assert report.safe_to_replan
    assert not report.requires_verification
    assert report.attempt.state is ExecutionAttemptState.AUTHORIZED


def test_recovery_abandoned_attempt_requires_replan():
    target = store()
    item = reserve(target)
    target.abandon(item)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert report.disposition is AttemptRecoveryDisposition.REPLAN
    assert report.safe_to_replan
    assert "abandoned" in report.reasons[0]


def test_recovery_boundary_entered_requires_verification():
    target = store()
    item = reserve(target)
    target.enter_boundary(item)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert report.disposition is AttemptRecoveryDisposition.VERIFY
    assert report.requires_verification
    assert not report.safe_to_replan
    assert "crossed process boundary" in report.reasons[0]


def test_recovery_success_with_terminal_evidence_is_terminal():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.succeed(item, terminal_evidence_digest=fp("e"))
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(
            terminal_evidence_digest=fp("e"),
        ),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.TERMINAL_SUCCESS
    )
    assert report.authority_matches
    assert report.attempt.terminal_evidence_digest == fp("e")


def test_recovery_failed_without_terminal_evidence_requires_verification():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.fail(item, error_type="RuntimeError")
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert report.disposition is AttemptRecoveryDisposition.VERIFY
    assert report.requires_verification
    assert "without terminal evidence" in report.reasons[0]


def test_recovery_failed_with_terminal_evidence_is_terminal_failure():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.fail(
        item,
        error_type="ExecutionOrVerificationFailed",
        terminal_evidence_digest=fp("e"),
    )
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(
            terminal_evidence_digest=fp("e"),
        ),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.TERMINAL_FAILURE
    )
    assert not report.requires_verification


@pytest.mark.parametrize(
    "field,value,phrase",
    [
        ("principal", "bob", "principal mismatch"),
        ("worker_id", "worker-2", "worker mismatch"),
        ("plan_fingerprint", fp("x"), "plan mismatch"),
        ("execution_seal_id", "seal-2", "execution seal mismatch"),
        ("runtime_trust_digest", fp("x"), "runtime trust mismatch"),
        ("release_evidence_digest", fp("x"), "release evidence mismatch"),
        ("execution_backend_id", "other", "execution backend mismatch"),
    ],
)
def test_recovery_expectation_mismatch_forces_manual_review(
    field,
    value,
    phrase,
):
    target = store()
    reserve(target)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(**{field: value}),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.MANUAL_REVIEW
    )
    assert not report.authority_matches
    assert not report.safe_to_replan
    assert any(phrase in reason for reason in report.reasons)


def test_recovery_terminal_evidence_mismatch_forces_manual_review():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.succeed(item, terminal_evidence_digest=fp("e"))
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(
            terminal_evidence_digest=fp("x"),
        ),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.MANUAL_REVIEW
    )
    assert any(
        "terminal evidence mismatch" in reason
        for reason in report.reasons
    )


def test_recovery_expectation_can_be_partial():
    target = store()
    reserve(target)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=AttemptRecoveryExpectation(
            principal="alice",
        ),
    )
    assert report.disposition is AttemptRecoveryDisposition.REPLAN
    assert report.authority_matches


def test_recovery_empty_expectation_accepts_current_authority():
    target = store()
    reserve(target)
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session"
    )
    assert report.disposition is AttemptRecoveryDisposition.REPLAN
    assert report.authority_matches


def test_recovery_report_to_dict_contains_attempt_and_controls():
    target = store()
    reserve(target)
    expected = expectation()
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expected,
    )
    data = report.to_dict()
    assert data["session_id"] == "session"
    assert data["disposition"] == "replan"
    assert data["attempt_id"] == "seal-1"
    assert data["authority_matches"] is True
    assert data["safe_to_replan"] is True
    assert data["requires_verification"] is False
    assert data["expectation_digest"] == expected.digest
    assert data["attempt"]["attempt_id"] == "seal-1"


def test_recovery_expectation_digest_is_stable():
    first = expectation()
    second = expectation()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_recovery_expectation_digest_changes_with_trust():
    first = expectation(runtime_trust_digest=fp("a"))
    second = expectation(runtime_trust_digest=fp("b"))
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan_fingerprint", "bad"),
        ("runtime_trust_digest", "bad"),
        ("release_evidence_digest", "bad"),
        ("terminal_evidence_digest", "bad"),
    ],
)
def test_recovery_expectation_digest_validation(field, value):
    with pytest.raises(ValueError):
        AttemptRecoveryExpectation(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "principal",
        "worker_id",
        "execution_seal_id",
        "execution_backend_id",
    ],
)
def test_recovery_expectation_identity_limit(field):
    with pytest.raises(ValueError, match="too long"):
        AttemptRecoveryExpectation(**{field: "x" * 257})


@pytest.mark.parametrize("session_id", ["", "x" * 257])
def test_recovery_session_validation(session_id):
    with pytest.raises(ValueError, match="session_id"):
        AIExecutionAttemptRecoveryInspector(store()).inspect(session_id)


def test_recovery_inspector_requires_attempt_store():
    with pytest.raises(TypeError, match="AIExecutionAttemptStore"):
        AIExecutionAttemptRecoveryInspector(object())


def test_recovery_require_no_ambiguous_side_effects_allows_replan():
    target = store()
    reserve(target)
    report = AIExecutionAttemptRecoveryInspector(
        target
    ).require_no_ambiguous_side_effects(
        "session",
        expectation=expectation(),
    )
    assert report.disposition is AttemptRecoveryDisposition.REPLAN


def test_recovery_require_no_ambiguous_side_effects_blocks_boundary():
    target = store()
    item = reserve(target)
    target.enter_boundary(item)
    with pytest.raises(RuntimeError, match="crossed process boundary"):
        AIExecutionAttemptRecoveryInspector(
            target
        ).require_no_ambiguous_side_effects(
            "session",
            expectation=expectation(),
        )


def test_recovery_require_no_ambiguous_side_effects_blocks_mismatch():
    target = store()
    reserve(target)
    with pytest.raises(RuntimeError, match="principal mismatch"):
        AIExecutionAttemptRecoveryInspector(
            target
        ).require_no_ambiguous_side_effects(
            "session",
            expectation=expectation(principal="mallory"),
        )


def test_recovery_require_no_ambiguous_side_effects_allows_terminal_success():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.succeed(item, terminal_evidence_digest=fp("e"))
    report = AIExecutionAttemptRecoveryInspector(
        target
    ).require_no_ambiguous_side_effects(
        "session",
        expectation=expectation(
            terminal_evidence_digest=fp("e"),
        ),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.TERMINAL_SUCCESS
    )


def test_recovery_require_no_ambiguous_side_effects_allows_terminal_failure_with_evidence():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    target.fail(
        item,
        error_type="Failure",
        terminal_evidence_digest=fp("e"),
    )
    report = AIExecutionAttemptRecoveryInspector(
        target
    ).require_no_ambiguous_side_effects(
        "session",
        expectation=expectation(
            terminal_evidence_digest=fp("e"),
        ),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.TERMINAL_FAILURE
    )


def test_recovery_missing_attempt_is_not_claimed_safe_to_replan():
    report = AIExecutionAttemptRecoveryInspector(store()).inspect("session")
    assert report.disposition is AttemptRecoveryDisposition.NO_ATTEMPT
    assert not report.safe_to_replan


def test_recovery_session_head_authority_corruption_becomes_manual_review():
    target = store()
    stored = target.reserve(
        attempt_id="seal-1",
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        execution_backend_id="shell-service-host",
    )
    key = target.session_key("session")
    record = target.backend.get(target.namespace, key)
    target.backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=ExecutionAttemptSessionHead(
            "session",
            stored.attempt.attempt_id,
            fp("x"),
        ),
    )
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.MANUAL_REVIEW
    )
    assert not report.authority_matches
    assert any("authority mismatch" in reason for reason in report.reasons)


def test_recovery_session_head_missing_attempt_becomes_manual_review():
    target = store()
    stored = target.reserve(
        attempt_id="seal-1",
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        execution_seal_id="seal-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        execution_backend_id="shell-service-host",
    )
    key = target.key(stored.attempt.attempt_id)
    record = target.backend.get(target.namespace, key)
    target.backend.delete(
        target.namespace,
        key,
        expected_revision=record.revision,
    )
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session",
        expectation=expectation(),
    )
    assert (
        report.disposition
        is AttemptRecoveryDisposition.MANUAL_REVIEW
    )
    assert any("missing attempt" in reason for reason in report.reasons)


def test_recovery_current_attempt_is_exposed_for_terminal_failure():
    target = store()
    item = reserve(target)
    item = target.enter_boundary(item).attempt
    item = target.fail(
        item,
        error_type="SyntheticFailure",
        terminal_evidence_digest=fp("e"),
    ).attempt
    report = AIExecutionAttemptRecoveryInspector(target).inspect(
        "session"
    )
    assert report.attempt == item
    assert report.attempt.error_type == "SyntheticFailure"
    assert report.attempt.terminal_evidence_digest == fp("e")
