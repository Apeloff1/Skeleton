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
