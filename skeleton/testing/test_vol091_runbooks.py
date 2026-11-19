from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest

from skeleton.observability.runbooks import (
    Runbook,
    RunbookError,
    RunbookRegistry,
    RunbookStep,
    RunbookValidation,
    StepKind,
    ValidationStatus,
)

NOW = datetime(2026, 10, 5, 13, 50, 0, tzinfo=timezone.utc)
SHA = hashlib.sha256(b"drill-evidence").hexdigest()
ROOT = Path(__file__).resolve().parents[2]


def steps():
    return (
        RunbookStep(
            "STEP.OBSERVE",
            StepKind.OBSERVE,
            "Inspect queue depth",
            signal_ref="SIGNAL.QUEUE.DEPTH",
            next_step_ids=("STEP.DECIDE",),
        ),
        RunbookStep(
            "STEP.DECIDE",
            StepKind.DECISION,
            "Choose bounded recovery or escalation",
            condition_ref="COND.QUEUE.RECOVERABLE",
            next_step_ids=("STEP.ESCALATE", "STEP.RECOVER"),
        ),
        RunbookStep(
            "STEP.RECOVER",
            StepKind.COMMAND,
            "Restart the bounded worker",
            command_ref="CMD.WORKER.RESTART",
            authority_ref="AUTH.OPERATOR.RECOVERY",
            rollback_step_id="STEP.ROLLBACK",
            next_step_ids=("STEP.STOP",),
        ),
        RunbookStep(
            "STEP.ROLLBACK",
            StepKind.ROLLBACK,
            "Restore the previous worker generation",
            command_ref="CMD.WORKER.ROLLBACK",
            authority_ref="AUTH.OPERATOR.RECOVERY",
            next_step_ids=("STEP.STOP",),
        ),
        RunbookStep(
            "STEP.ESCALATE",
            StepKind.ESCALATE,
            "Escalate to the incident commander",
            condition_ref="COND.RECOVERY.UNSAFE",
        ),
        RunbookStep(
            "STEP.STOP",
            StepKind.STOP,
            "Stop automation and preserve evidence",
            condition_ref="COND.RECOVERY.COMPLETE",
        ),
    )


def book(version="V1", ordered_steps=None):
    return Runbook(
        "RUNBOOK.QUEUE.RECOVERY",
        version,
        "OWNER.SRE",
        "Read-only diagnostics; no autonomous mutation.",
        "STEP.OBSERVE",
        tuple(ordered_steps or steps()),
    )


def validation(
    target: Runbook,
    *,
    validation_id="VALIDATION.1",
    drill_id="DRILL.1",
    status=ValidationStatus.PASSED,
    **overrides,
):
    values = dict(
        validation_id=validation_id,
        runbook_id=target.runbook_id,
        runbook_version=target.version,
        runbook_digest=target.digest,
        drill_id=drill_id,
        validator_id="VALIDATOR.SRE",
        status=status,
        evidence_digest=SHA,
        observed_at=NOW,
        incident_ref=None,
    )
    values.update(overrides)
    return RunbookValidation(**values)


def test_runbook_identity_is_deterministic_across_step_order():
    first = book()
    second = book(ordered_steps=tuple(reversed(steps())))
    assert first == second
    assert first.digest == second.digest
    assert [step.step_id for step in first.steps] == sorted(
        step.step_id for step in first.steps
    )


def test_valid_runbook_binds_signals_commands_authority_rollback_and_terminal_conditions():
    target = book()
    recover = next(step for step in target.steps if step.step_id == "STEP.RECOVER")
    stop = next(step for step in target.steps if step.step_id == "STEP.STOP")
    assert recover.command_ref == "CMD.WORKER.RESTART"
    assert recover.authority_ref == "AUTH.OPERATOR.RECOVERY"
    assert recover.rollback_step_id == "STEP.ROLLBACK"
    assert stop.condition_ref == "COND.RECOVERY.COMPLETE"


def test_step_kind_must_be_typed():
    with pytest.raises(RunbookError, match="StepKind"):
        RunbookStep("STEP.BAD", "observe", "Look", signal_ref="SIGNAL.X")


def test_observe_requires_named_signal():
    with pytest.raises(RunbookError, match="signal_ref"):
        RunbookStep("STEP.OBS", StepKind.OBSERVE, "Look")


def test_command_requires_command_authority_and_explicit_rollback():
    with pytest.raises(RunbookError, match="command_ref and authority_ref"):
        RunbookStep(
            "STEP.CMD",
            StepKind.COMMAND,
            "Run",
            command_ref="CMD.RUN",
            rollback_step_id="STEP.ROLLBACK",
        )
    with pytest.raises(RunbookError, match="rollback_step_id"):
        RunbookStep(
            "STEP.CMD",
            StepKind.COMMAND,
            "Run",
            command_ref="CMD.RUN",
            authority_ref="AUTH.RUN",
        )


def test_rollback_requires_command_authority_and_cannot_chain_rollback():
    with pytest.raises(RunbookError, match="command_ref and authority_ref"):
        RunbookStep(
            "STEP.ROLLBACK",
            StepKind.ROLLBACK,
            "Restore",
            command_ref="CMD.RESTORE",
        )
    with pytest.raises(RunbookError, match="cannot declare"):
        RunbookStep(
            "STEP.ROLLBACK",
            StepKind.ROLLBACK,
            "Restore",
            command_ref="CMD.RESTORE",
            authority_ref="AUTH.RESTORE",
            rollback_step_id="STEP.OTHER",
        )


def test_terminal_steps_require_explicit_condition_and_no_successors():
    with pytest.raises(RunbookError, match="condition_ref"):
        RunbookStep("STEP.STOP", StepKind.STOP, "Stop")
    with pytest.raises(RunbookError, match="terminal"):
        RunbookStep(
            "STEP.STOP",
            StepKind.STOP,
            "Stop",
            condition_ref="COND.STOP",
            next_step_ids=("STEP.X",),
        )


def test_successors_must_be_typed_unique_and_not_direct_self_loop():
    with pytest.raises(RunbookError, match="tuple"):
        RunbookStep(
            "STEP.DECIDE",
            StepKind.DECISION,
            "Choose",
            next_step_ids=["STEP.STOP"],
        )
    with pytest.raises(RunbookError, match="duplicate successor"):
        RunbookStep(
            "STEP.DECIDE",
            StepKind.DECISION,
            "Choose",
            next_step_ids=("STEP.STOP", "STEP.STOP"),
        )
    with pytest.raises(RunbookError, match="directly succeed itself"):
        RunbookStep(
            "STEP.DECIDE",
            StepKind.DECISION,
            "Choose",
            next_step_ids=("STEP.DECIDE",),
        )


def test_unknown_successor_and_rollback_fail_closed():
    altered = list(steps())
    altered[0] = RunbookStep(
        "STEP.OBSERVE",
        StepKind.OBSERVE,
        "Look",
        signal_ref="SIGNAL.X",
        next_step_ids=("STEP.MISSING",),
    )
    with pytest.raises(RunbookError, match="unknown successor"):
        book(ordered_steps=altered)

    altered = list(steps())
    recover = altered[2]
    altered[2] = RunbookStep(
        recover.step_id,
        recover.kind,
        recover.instruction,
        command_ref=recover.command_ref,
        authority_ref=recover.authority_ref,
        rollback_step_id="STEP.MISSING",
        next_step_ids=recover.next_step_ids,
    )
    with pytest.raises(RunbookError, match="unknown rollback"):
        book(ordered_steps=altered)


def test_rollback_target_must_be_rollback_step():
    altered = list(steps())
    recover = altered[2]
    altered[2] = RunbookStep(
        recover.step_id,
        recover.kind,
        recover.instruction,
        command_ref=recover.command_ref,
        authority_ref=recover.authority_ref,
        rollback_step_id="STEP.STOP",
        next_step_ids=recover.next_step_ids,
    )
    with pytest.raises(RunbookError, match="rollback target"):
        book(ordered_steps=altered)


def test_rollback_edge_counts_as_reachable_recovery_path():
    target = book()
    assert any(step.step_id == "STEP.ROLLBACK" for step in target.steps)


def test_unreachable_steps_are_rejected():
    target_steps = (
        RunbookStep(
            "STEP.START",
            StepKind.STOP,
            "Stop",
            condition_ref="COND.DONE",
        ),
        RunbookStep(
            "STEP.ORPHAN",
            StepKind.STOP,
            "Orphan",
            condition_ref="COND.ORPHAN",
        ),
    )
    with pytest.raises(RunbookError, match="unreachable"):
        Runbook(
            "RUNBOOK.X",
            "V1",
            "OWNER.OPS",
            "Read only.",
            "STEP.START",
            target_steps,
        )


def test_reachable_nonterminating_cycle_is_rejected():
    target_steps = (
        RunbookStep(
            "STEP.START",
            StepKind.DECISION,
            "Choose",
            next_step_ids=("STEP.LOOP", "STEP.STOP"),
        ),
        RunbookStep(
            "STEP.LOOP",
            StepKind.DECISION,
            "Loop between two states",
            next_step_ids=("STEP.LOOP2",),
        ),
        RunbookStep(
            "STEP.LOOP2",
            StepKind.DECISION,
            "Loop back",
            next_step_ids=("STEP.LOOP",),
        ),
        RunbookStep(
            "STEP.STOP",
            StepKind.STOP,
            "Stop",
            condition_ref="COND.DONE",
        ),
    )
    with pytest.raises(RunbookError, match="path to stop or escalation"):
        Runbook(
            "RUNBOOK.LOOP",
            "V1",
            "OWNER.OPS",
            "Read only.",
            "STEP.START",
            target_steps,
        )


def test_cycle_with_exit_to_terminal_is_allowed():
    target_steps = (
        RunbookStep(
            "STEP.START",
            StepKind.DECISION,
            "Enter retry loop",
            next_step_ids=("STEP.LOOP",),
        ),
        RunbookStep(
            "STEP.LOOP",
            StepKind.DECISION,
            "Retry or stop",
            next_step_ids=("STEP.RETRY", "STEP.STOP"),
        ),
        RunbookStep(
            "STEP.RETRY",
            StepKind.DECISION,
            "Return to retry decision",
            next_step_ids=("STEP.LOOP",),
        ),
        RunbookStep(
            "STEP.STOP",
            StepKind.STOP,
            "Stop",
            condition_ref="COND.DONE",
        ),
    )
    assert Runbook(
        "RUNBOOK.RETRY",
        "V1",
        "OWNER.OPS",
        "Read only.",
        "STEP.START",
        target_steps,
    ).entry_step_id == "STEP.START"


def test_runbook_version_identity_is_immutable():
    registry = RunbookRegistry()
    registry.register(book())
    changed = Runbook(
        "RUNBOOK.QUEUE.RECOVERY",
        "V1",
        "OWNER.OTHER",
        "Read only.",
        "STEP.OBSERVE",
        steps(),
    )
    with pytest.raises(RunbookError, match="immutable"):
        registry.register(changed)


def test_registry_registration_is_idempotent():
    registry = RunbookRegistry()
    target = book()
    assert registry.register(target) is target
    assert registry.register(target) is target


def test_drill_must_bind_exact_runbook_id_version_and_digest():
    registry = RunbookRegistry()
    one = book("V1")
    two = book("V2")
    registry.register(one)
    registry.register(two)

    with pytest.raises(RunbookError, match="exact runbook version"):
        registry.record_validation(
            validation(one, runbook_version="V2")
        )
    with pytest.raises(RunbookError, match="exact runbook version"):
        registry.record_validation(
            validation(one, runbook_digest="b" * 64)
        )


def test_validation_status_and_timestamp_are_strict():
    target = book()
    with pytest.raises(RunbookError, match="ValidationStatus"):
        validation(target, status="passed")
    with pytest.raises(RunbookError, match="timezone-aware"):
        validation(
            target,
            observed_at=datetime(2026, 10, 5, 13, 50, 0),
        )
    with pytest.raises(RunbookError, match="whole-second"):
        validation(
            target,
            observed_at=NOW.replace(microsecond=1),
        )


def test_validation_digest_binds_validator_time_and_incident():
    target = book()
    first = validation(target)
    second = validation(
        target,
        validation_id="VALIDATION.2",
        validator_id="VALIDATOR.OTHER",
        incident_ref="INCIDENT.42",
    )
    assert first.digest != second.digest


def test_passed_drill_validates_only_exact_runbook_version():
    registry = RunbookRegistry()
    one = book("V1")
    two = book("V2")
    registry.register(one)
    registry.register(two)
    registry.record_validation(validation(one))

    assert registry.validated(one.runbook_id, "V1") is True
    assert registry.validated(two.runbook_id, "V2") is False


def test_failed_drill_does_not_validate():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    registry.record_validation(
        validation(target, status=ValidationStatus.FAILED)
    )
    assert registry.validated(target.runbook_id, target.version) is False


def test_duplicate_drill_receipt_for_exact_runbook_is_rejected():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    registry.record_validation(validation(target))
    with pytest.raises(RunbookError, match="drill identity"):
        registry.record_validation(
            validation(
                target,
                validation_id="VALIDATION.2",
                status=ValidationStatus.FAILED,
            )
        )


def test_identical_validation_replay_is_idempotent():
    registry = RunbookRegistry()
    target = book()
    item = validation(target)
    registry.register(target)
    assert registry.record_validation(item) is item
    assert registry.record_validation(item) is item


def test_validation_listing_is_chronological_and_version_scoped():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    later = validation(
        target,
        validation_id="VALIDATION.LATER",
        drill_id="DRILL.LATER",
        observed_at=datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc),
    )
    earlier = validation(
        target,
        validation_id="VALIDATION.EARLIER",
        drill_id="DRILL.EARLIER",
        observed_at=datetime(2026, 10, 5, 13, 0, 0, tzinfo=timezone.utc),
    )
    registry.record_validation(later)
    registry.record_validation(earlier)
    assert registry.validations_for(target.runbook_id, target.version) == (
        earlier,
        later,
    )


def test_registry_digest_is_order_independent():
    first = RunbookRegistry()
    second = RunbookRegistry()
    one = book("V1")
    two = book("V2")
    first.register(one)
    first.register(two)
    second.register(two)
    second.register(one)
    assert first.digest == second.digest


def test_canonical_and_governed_ai_runbooks_are_byte_identical():
    assert (
        ROOT / "skeleton/observability/runbooks.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/observability/runbooks.py"
    ).read_bytes()


def test_canonical_and_governed_observability_exports_are_byte_identical():
    assert (
        ROOT / "skeleton/observability/__init__.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/observability/__init__.py"
    ).read_bytes()

def test_newer_failed_drill_invalidates_older_pass():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    registry.record_validation(validation(target, validation_id="VALIDATION.PASS", drill_id="DRILL.PASS", observed_at=NOW, status=ValidationStatus.PASSED))
    registry.record_validation(validation(target, validation_id="VALIDATION.FAIL", drill_id="DRILL.FAIL", observed_at=datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc), status=ValidationStatus.FAILED))
    assert registry.validated(target.runbook_id, target.version) is False

def test_newer_pass_can_revalidate_after_older_failure():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    registry.record_validation(validation(target, validation_id="VALIDATION.FAIL", drill_id="DRILL.FAIL", observed_at=NOW, status=ValidationStatus.FAILED))
    registry.record_validation(validation(target, validation_id="VALIDATION.PASS", drill_id="DRILL.PASS", observed_at=datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc), status=ValidationStatus.PASSED))
    assert registry.validated(target.runbook_id, target.version) is True

def test_conflicting_latest_drills_fail_closed():
    registry = RunbookRegistry()
    target = book()
    registry.register(target)
    registry.record_validation(validation(target, validation_id="VALIDATION.PASS", drill_id="DRILL.PASS", observed_at=NOW, status=ValidationStatus.PASSED))
    registry.record_validation(validation(target, validation_id="VALIDATION.FAIL", drill_id="DRILL.FAIL", observed_at=NOW, status=ValidationStatus.FAILED))
    assert registry.validated(target.runbook_id, target.version) is False
