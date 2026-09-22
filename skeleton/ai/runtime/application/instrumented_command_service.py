"""Lifecycle-aware wrapper for the transport-neutral command service.

The wrapper keeps execution tracking outside handlers while providing a single
runtime attachment point for evidence and reconciliation systems.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .command_contracts import CommandResult, CommandService
from .command_execution_lifecycle import CommandExecutionLifecycle


class InstrumentedCommandService:
    """Attach execution lifecycle tracking without changing handlers."""

    def __init__(
        self,
        service: CommandService,
        lifecycle: Optional[CommandExecutionLifecycle] = None,
    ) -> None:
        self.service = service
        self.lifecycle = lifecycle or CommandExecutionLifecycle()

    def execute(
        self,
        command: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> CommandResult:
        execution_id = self.lifecycle.begin(command, payload)
        result = self.service.execute(command, payload)

        if result.ok:
            self.lifecycle.succeed(execution_id, result.to_payload())
        else:
            error = result.error.message if result.error else "unknown failure"
            self.lifecycle.fail(execution_id, error)

        return result
