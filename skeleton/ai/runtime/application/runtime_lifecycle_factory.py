"""Factories for runtime lifecycle-aware command execution.

Keeps construction concerns separate from command contracts and handlers.
"""

from __future__ import annotations

from .command_contracts import CommandService
from .command_execution_lifecycle import CommandExecutionLifecycle
from .instrumented_command_service import InstrumentedCommandService


def build_lifecycle_command_service(
    service: CommandService,
    lifecycle: CommandExecutionLifecycle | None = None,
) -> InstrumentedCommandService:
    """Wrap a command service with execution tracking.

    The factory intentionally does not alter handlers, contracts, or transports.
    It only composes the runtime lifecycle boundary.
    """

    return InstrumentedCommandService(
        service=service,
        lifecycle=lifecycle or CommandExecutionLifecycle(),
    )
