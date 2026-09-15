"""Application-layer contracts shared by CLI and API surfaces."""

from .command_contracts import (
    CONTRACT_VERSION,
    CommandError,
    CommandResult,
    CommandService,
    CommandSpec,
    command_specs,
    parity_matrix,
)
from .runtime_commands import build_runtime_command_service

__all__ = [
    "CONTRACT_VERSION",
    "CommandError",
    "CommandResult",
    "CommandService",
    "CommandSpec",
    "build_runtime_command_service",
    "command_specs",
    "parity_matrix",
]
