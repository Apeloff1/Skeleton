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
from .deployment_profiles import (
    AirGapProfile,
    Connectivity,
    DeferredOperation,
    DeferredSyncLedger,
    EdgeNode,
    EdgeProfile,
    EnterpriseProfile,
    EnterpriseTopology,
    OfflineProfile,
    SyncReceipt,
    SyncState,
    TransferBundle,
    admit_transfer,
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
    "CapabilityRegistry",
    "CapabilitySpec",
    "ContractFuzzer",
    "FuzzBudget",
    "FuzzFailure",
    "FuzzReport",
    "DEFERRED_165_SPECS",
    "AirGapProfile",
    "Connectivity",
    "DeferredOperation",
    "DeferredSyncLedger",
    "EdgeNode",
    "EdgeProfile",
    "EnterpriseProfile",
    "EnterpriseTopology",
    "OfflineProfile",
    "SyncReceipt",
    "SyncState",
    "TransferBundle",
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
    "SimulationAuthority",
    "SimulationEvidence",
    "SimulationRequest",
    "SimulationResult",
    "SimulationRuntime",
    "SqliteDeferredExecutionJournal",
    "build_registry",
    "admit_transfer",
    "volume_ids",
]
