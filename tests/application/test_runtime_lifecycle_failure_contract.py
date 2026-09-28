"""Regression coverage for lifecycle failure classification."""

from skeleton.application.command_contracts import CommandService
from skeleton.application.command_execution_lifecycle import CommandExecutionLifecycle
from skeleton.application.instrumented_command_service import InstrumentedCommandService


def test_failed_command_records_failure_evidence():
    service = CommandService()
    service.register("status", lambda _: (_ for _ in ()).throw(ValueError("bad state")))

    lifecycle = CommandExecutionLifecycle()
    instrumented = InstrumentedCommandService(service=service, lifecycle=lifecycle)

    result = instrumented.execute("status", {})

    assert result.ok is False
    assert result.error is not None
    assert len(lifecycle.ledger.snapshot()) == 1
    assert lifecycle.ledger.snapshot()[0].status == "failed"

def test_successful_command_records_success_evidence():
    lifecycle = CommandExecutionLifecycle()
    execution_id = lifecycle.begin("status", {"mode": "ok"})

    lifecycle.succeed(execution_id, {"value": 1})

    records = lifecycle.ledger.snapshot()
    assert len(records) == 1
    assert records[0].status == "succeeded"
    assert records[0].evidence == {"result_keys": ["value"]}


def test_retryable_failure_preserves_retryable_status():
    lifecycle = CommandExecutionLifecycle()
    execution_id = lifecycle.begin("status", {})

    lifecycle.fail(
        execution_id,
        "temporary provider failure",
        retryable=True,
    )

    records = lifecycle.ledger.snapshot()
    assert len(records) == 1
    assert records[0].status == "retryable"
    assert records[0].evidence == {
        "error": "temporary provider failure"
    }

