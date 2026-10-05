"""Deferred AI frontier runtime.

This package materializes executable ownership for the 165 volumes that remain
queued by the canonical masterplan continuation frontier.  It never grants
masterplan completion authority.
"""
from .catalog import DEFERRED_165_SPECS, build_registry, volume_ids
from .contracts import CapabilityRegistry, CapabilitySpec, EvidenceReceipt
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
from .simulation_mode import (
    SimulationAuthority,
    SimulationEvidence,
    SimulationRequest,
    SimulationResult,
    SimulationRuntime,
)
from .journal import (
    DeferredExecutionJournal,
    DeferredJournalConflict,
    DeferredJournalError,
    DeferredJournalRecord,
    SqliteDeferredExecutionJournal,
)

__all__ = [
    "CapabilityRegistry",
    "CapabilitySpec",
    "DEFERRED_165_SPECS",
    "DeferredEffectAuthority",
    "DeferredExecutionError",
    "DeferredExecutionJournal",
    "DeferredExecutionPendingError",
    "DeferredExecutor",
    "DeferredJournalConflict",
    "DeferredJournalError",
    "DeferredJournalRecord",
    "DeferredInvocation",
    "EvidenceReceipt",
    "ExecutionOutcome",
    "ExecutionReceipt",
    "FailureReceipt",
    "SqliteDeferredExecutionJournal",
    "SimulationAuthority",
    "SimulationEvidence",
    "SimulationRequest",
    "SimulationResult",
    "SimulationRuntime",
    "build_registry",
    "volume_ids",
]
