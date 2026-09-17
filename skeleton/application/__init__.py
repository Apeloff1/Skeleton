"""Application-layer contracts shared by CLI and API surfaces."""

from .capability_manifest import (
    CAPABILITIES,
    CAPABILITIES_BY_ID,
    CAPABILITY_MANIFEST_VERSION,
    Capability,
    capability_manifest,
    get_capability,
)
from .capability_runtime import (
    CAPABILITY_LOADER,
    CapabilityLoadError,
    CapabilityLoader,
    CapabilityRuntimeStatus,
    capability_runtime_status,
    load_capability,
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
from .sota_program import (
    LANES,
    LANES_BY_ID,
    SOTA_PROGRAM_ISSUE,
    SOTA_PROGRAM_VERSION,
    SotaLane,
    get_lane,
    sota_program,
)

__all__ = [
    "CAPABILITIES",
    "CAPABILITIES_BY_ID",
    "CAPABILITY_LOADER",
    "CAPABILITY_MANIFEST_VERSION",
    "CONTRACT_VERSION",
    "LANES",
    "LANES_BY_ID",
    "SOTA_PROGRAM_ISSUE",
    "SOTA_PROGRAM_VERSION",
    "Capability",
    "CapabilityLoadError",
    "CapabilityLoader",
    "CapabilityRuntimeStatus",
    "CommandError",
    "CommandResult",
    "CommandService",
    "CommandSpec",
    "SotaLane",
    "build_runtime_command_service",
    "capability_manifest",
    "capability_runtime_status",
    "command_specs",
    "get_capability",
    "get_lane",
    "load_capability",
    "parity_matrix",
    "sota_program",
]
