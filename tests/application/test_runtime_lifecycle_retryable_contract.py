"""Regression coverage for retryable execution lifecycle states."""

from skeleton.application.command_contracts import CommandService
from skeleton.application.command_execution_lifecycle import CommandExecutionLifecycle
from skeleton.application.instrumented_command_service import InstrumentedCommandService


def test_retryable_failure_records_retry_state() -> None:
    service = CommandService()
    lifecycle = CommandExecutionLifecycle()
    wrapped = InstrumentedCommandService(service=service, lifecycle=lifecycle)

    execution_id = lifecycle.begin("status", {})
    lifecycle.fail(execution_id, "temporary dependency failure", retryable=True)

    record = lifecycle.ledger.get(execution_id)

    assert record is not None
    assert record.status == "retryable"
    assert record.evidence["error"] == "temporary dependency failure"
