"""Regression checks for lifecycle-aware command construction."""

from skeleton.application.command_contracts import CommandResult
from skeleton.application.runtime_lifecycle_factory import build_lifecycle_command_service


def test_lifecycle_factory_preserves_command_service_shape() -> None:
    service = build_lifecycle_command_service()

    assert hasattr(service, "execute")
    assert hasattr(service, "ledger")


def test_lifecycle_factory_tracks_successful_execution() -> None:
    service = build_lifecycle_command_service()

    service.register("status", lambda payload: {"ready": True})
    result: CommandResult = service.execute("status", {})

    assert result.ok is True
    records = service.ledger.snapshot()

    assert len(records) == 1
    assert records[0].status == "succeeded"
