"""Application-layer contracts shared by CLI and API surfaces."""

from .capability_manifest import (
    CAPABILITIES,
    CAPABILITY_MANIFEST_VERSION,
    Capability,
    capability_manifest,
)
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
    "CAPABILITIES",
    "CAPABILITY_MANIFEST_VERSION",
    "CONTRACT_VERSION",
    "Capability",
    "CommandError",
    "CommandResult",
    "CommandService",
    "CommandSpec",
    "build_runtime_command_service",
    "capability_manifest",
    "command_specs",
    "parity_matrix",
]
