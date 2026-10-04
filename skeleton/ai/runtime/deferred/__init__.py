"""Deferred AI frontier runtime.

This package materializes executable ownership for the 165 volumes that remain
queued by the canonical masterplan continuation frontier.  It never grants
masterplan completion authority.
"""
from .catalog import DEFERRED_165_SPECS, build_registry, volume_ids
from .contracts import CapabilityRegistry, CapabilitySpec, EvidenceReceipt
from .executor import (
    DeferredExecutionError,
    DeferredExecutionPendingError,
    DeferredExecutor,
    DeferredInvocation,
    ExecutionOutcome,
    ExecutionReceipt,
    FailureReceipt,
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
    "build_registry",
    "volume_ids",
]
