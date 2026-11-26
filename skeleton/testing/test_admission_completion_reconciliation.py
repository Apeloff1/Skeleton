"""Admission completion survives a crash after a terminal commit.

Maintenance that only scans nonterminal executions cannot see this work.
Reconciliation uses the completion record written in the existing finalization
outbox and does not dispatch the model. A staged intent is not a commit.
"""
from __future__ import annotations

from skeleton.contracts.ai_execution import (
    AIExecutionResult,
    ExecutionState,
    execution_payload_digest,
)
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.testing.test_engine_execution_coordinator import (
    _admitted_service,
    _bundle,
    _now,
)


def _submit(service, execution_id: str):
    _operation, command = _bundle(execution_id=execution_id)
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    return command


def _advance(repo, execution_id: str):
    current = repo.get(execution_id)
    for state in (
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
        ExecutionState.VERIFYING,
    ):
        current = repo.transition(
            execution_id,
            state,
            expected_version=current.version,
            now=_now(),
        )
    return current


def _result(command) -> AIExecutionResult:
    request = command.execution_request
    return AIExecutionResult(
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        status="completed",
        final_output="local review answer",
        verification="verification:local-review",
        usage={"input_tokens": 3, "output_tokens": 2},
        completed_at=_now(),
    )


def test_crash_between_commit_and_completion_reconciles_without_provider(tmp_path, monkeypatch) -> None:
    service, _runtime, ledger = _admitted_service(tmp_path)
    command = _submit(service, "local-review-commit")
    repo = service.repository
    current = _advance(repo, "local-review-commit")
    result = _result(command)
    repo.finalize(result, expected_execution_version=current.version, now=_now())

    def dispatched(*_args, **_kwargs):
        raise AssertionError("admission reconciliation dispatched the model")

    monkeypatch.setattr(CognitiveExecutionRuntime, "start", dispatched)
    monkeypatch.setattr(CognitiveExecutionRuntime, "resume", dispatched)

    pending = repo.pending_admission_completions()
    assert len(pending) == 1
    record = pending[0]
    assert record.operation_id == command.execution_request.operation_id
    assert record.request_digest == command.execution_request.identity_digest
    assert record.receipt_digest == execution_payload_digest(result.as_dict())
    assert record.completed_at is None
    assert ledger.snapshot("tenant-a")["active_reservations"] == 1
    assert repo.result("local-review-commit") == result

    applied = service.reconcile_admission_completions(now=_now())
    assert [item.outbox_id for item in applied] == [record.outbox_id]
    assert applied[0].completed_at is not None
    closed = ledger.snapshot("tenant-a")
    assert closed["active_reservations"] == 0
    assert closed["committed"]["operations"] == 1

    replayed = service.reconcile_admission_completions(now=_now())
    direct = service.reconcile_admission_completion(record.outbox_id, now=_now())
    assert replayed == ()
    assert direct is not None
    assert direct.completed_at == applied[0].completed_at
    assert direct.operation_id == record.operation_id
    assert direct.request_digest == record.request_digest
    assert direct.receipt_digest == record.receipt_digest
    assert ledger.snapshot("tenant-a")["committed"]["operations"] == 1
    assert repo.pending_admission_completions() == ()
    assert repo.result("local-review-commit") == result


def test_staged_result_is_not_completed_or_published(tmp_path, monkeypatch) -> None:
    service, _runtime, ledger = _admitted_service(tmp_path)
    command = _submit(service, "local-review-staged")
    repo = service.repository
    current = _advance(repo, "local-review-staged")
    result = _result(command)

    def dispatched(*_args, **_kwargs):
        raise AssertionError("staged reconciliation dispatched the model")

    monkeypatch.setattr(CognitiveExecutionRuntime, "start", dispatched)
    monkeypatch.setattr(CognitiveExecutionRuntime, "resume", dispatched)

    staged = repo.stage_finalization(
        result,
        expected_execution_version=current.version,
        now=_now(),
    )
    assert staged.result == result
    assert repo.result("local-review-staged") is None
    assert repo.get("local-review-staged").terminal is False
    assert repo.pending_admission_completions() == ()

    assert service.reconcile_admission_completions(now=_now()) == ()
    assert ledger.snapshot("tenant-a")["active_reservations"] == 1
    assert ledger.snapshot("tenant-a")["committed"]["operations"] == 0
    assert repo.result("local-review-staged") is None
    assert repo.finalization_intent("local-review-staged") is not None
