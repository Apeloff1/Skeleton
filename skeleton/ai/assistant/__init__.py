"""Clean-room product-assistant control plane for the canonical AI tree.

The package composes Skeleton's existing model, memory, tool, artifact and
automation planes. It contains no vendor model weights, hidden prompts, private
reasoning traces or proprietary provider implementation.
"""

from .artifacts import ArtifactRoute, ArtifactRouter
from .automation import (
    AutomationAdmission,
    AutomationBuilder,
    AutomationPolicy,
    AutomationPolicyError,
)
from .capabilities import (
    CapabilityAdmissionError,
    CapabilityAuthorizer,
    CapabilityDecision,
    CapabilityRegistry,
)
from .context import ContextCompiler
from .contracts import (
    ASSISTANT_SCHEMA_VERSION,
    ArtifactKind,
    AssistantContractError,
    AssistantRequest,
    AutomationIntent,
    CapabilityDescriptor,
    CapabilityGrant,
    CapabilityKind,
    CapabilityPlanStep,
    CompiledContext,
    ContextCandidate,
    IntentSignals,
    RoutingPlan,
    SideEffectClass,
    TimingMode,
    ToolProposal,
    ToolReceipt,
    TrustTier,
    deterministic_id,
    digest_json,
)
from .handoff import AssistantHandoff, build_handoff
from .memory import (
    MemoryAction,
    MemoryCandidate,
    MemoryDecision,
    MemoryPolicy,
    MemorySensitivity,
)
from .provenance import AssistantRunRecord, ProvenanceBuilder, receipt_digest
from .routing import AssistantRouter, infer_signals
from .runtime import AssistantControlPlane, AssistantPreparation
from .tooling import (
    CapabilityHandler,
    ToolCoordinator,
    ToolCoordinatorError,
    ToolRunResult,
)

__all__ = [
    "ASSISTANT_SCHEMA_VERSION",
    "ArtifactKind",
    "ArtifactRoute",
    "ArtifactRouter",
    "AssistantContractError",
    "AssistantControlPlane",
    "AssistantHandoff",
    "AssistantPreparation",
    "AssistantRequest",
    "AssistantRouter",
    "AssistantRunRecord",
    "AutomationAdmission",
    "AutomationBuilder",
    "AutomationIntent",
    "AutomationPolicy",
    "AutomationPolicyError",
    "CapabilityAdmissionError",
    "CapabilityAuthorizer",
    "CapabilityDecision",
    "CapabilityDescriptor",
    "CapabilityGrant",
    "CapabilityHandler",
    "CapabilityKind",
    "CapabilityPlanStep",
    "CapabilityRegistry",
    "CompiledContext",
    "ContextCandidate",
    "ContextCompiler",
    "IntentSignals",
    "MemoryAction",
    "MemoryCandidate",
    "MemoryDecision",
    "MemoryPolicy",
    "MemorySensitivity",
    "ProvenanceBuilder",
    "RoutingPlan",
    "SideEffectClass",
    "TimingMode",
    "ToolCoordinator",
    "ToolCoordinatorError",
    "ToolProposal",
    "ToolReceipt",
    "ToolRunResult",
    "TrustTier",
    "build_handoff",
    "deterministic_id",
    "digest_json",
    "infer_signals",
    "receipt_digest",
]
