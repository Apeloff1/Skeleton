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
    capability_lifecycle_snapshot,
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
from .plane_audit import AUDITED_PLANE_IDS, PLANE_AUDIT_KIND, plane_audit_snapshot
from .runtime_commands import build_runtime_command_service

__all__ = [
    "AUDITED_PLANE_IDS",
    "CAPABILITIES",
    "CAPABILITIES_BY_ID",
    "CAPABILITY_LOADER",
    "CAPABILITY_MANIFEST_VERSION",
    "CONTRACT_VERSION",
    "PLANE_AUDIT_KIND",
    "Capability",
    "CapabilityLoadError",
    "CapabilityLoader",
    "CapabilityRuntimeStatus",
    "CommandError",
    "CommandResult",
    "CommandService",
    "CommandSpec",
    "build_runtime_command_service",
    "capability_lifecycle_snapshot",
    "capability_manifest",
    "capability_runtime_status",
    "command_specs",
    "get_capability",
    "load_capability",
    "parity_matrix",
    "plane_audit_snapshot",
]
