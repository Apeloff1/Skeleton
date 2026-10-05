"""Deferred AI frontier runtime.

This package materializes executable ownership for the 165 volumes that remain
queued by the canonical masterplan continuation frontier.  It never grants
masterplan completion authority.
"""
from .catalog import DEFERRED_165_SPECS, build_registry, volume_ids
from .contracts import CapabilityRegistry, CapabilitySpec, EvidenceReceipt
from .card_systems import (
    AgentCard,
    CardClaim,
    CardRegistry,
    ClaimKind,
    DatasetCard,
    EvidenceRef,
    ModelCard,
    ToolCard,
)
from .executor import (
    DeferredEffectAuthority,
    DeferredExecutionError,
    DeferredExecutionPendingError,
    DeferredExecutor,
    DeferredInvocation,
    ExecutionOutcome,
    ExecutionReceipt,
    FailureReceipt,
)
from .epistemic_integrity import (
    CausalClaim, CausalGraph, CausalMethod, EvidenceDirection, Hypothesis,
    HypothesisEngine, HypothesisEvidence, HypothesisStatus, InterventionResult,
    KnowledgeRevision, TemporalClaim, TemporalKnowledge, ValidityInterval,
)
from .contract_fuzzing import ContractFuzzer, FuzzBudget, FuzzFailure, FuzzReport
from .simulation_mode import SimulationAuthority, SimulationEvidence, SimulationRequest, SimulationResult, SimulationRuntime
from .journal import (
    DeferredExecutionJournal,
    DeferredJournalConflict,
    DeferredJournalError,
    DeferredJournalRecord,
    SqliteDeferredExecutionJournal,
)

__all__ = [
    "AgentCard",
    "CardClaim",
    "CardRegistry",
    "ClaimKind",
    "CapabilityRegistry",
    "CapabilitySpec",
    "ContractFuzzer",
    "FuzzBudget",
    "FuzzFailure",
    "FuzzReport",
    "DEFERRED_165_SPECS",
    "DatasetCard",
    "CausalClaim",
    "CausalGraph",
    "CausalMethod",
    "EvidenceDirection",
    "Hypothesis",
    "HypothesisEngine",
    "HypothesisEvidence",
    "HypothesisStatus",
    "InterventionResult",
    "KnowledgeRevision",
    "TemporalClaim",
    "TemporalKnowledge",
    "ValidityInterval",
    "DeferredEffectAuthority",
    "DeferredExecutionError",
    "DeferredExecutionJournal",
    "DeferredExecutionPendingError",
    "DeferredExecutor",
    "DeferredJournalConflict",
    "DeferredJournalError",
    "DeferredJournalRecord",
    "DeferredInvocation",
    "EvidenceRef",
    "EvidenceReceipt",
    "ExecutionOutcome",
    "ExecutionReceipt",
    "FailureReceipt",
    "ModelCard",
    "SimulationAuthority",
    "SimulationEvidence",
    "SimulationRequest",
    "SimulationResult",
    "SimulationRuntime",
    "SqliteDeferredExecutionJournal",
    "ToolCard",
    "build_registry",
    "volume_ids",
]
