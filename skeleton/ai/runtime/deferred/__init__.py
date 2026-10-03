"""Deferred AI frontier runtime.

This package materializes executable ownership for the 165 volumes that remain
queued by the canonical masterplan continuation frontier.  It never grants
masterplan completion authority.
"""
from .catalog import DEFERRED_165_SPECS, build_registry, volume_ids
from .contracts import CapabilityRegistry, CapabilitySpec, EvidenceReceipt
from .planner import (
    DeferredPlan,
    DeferredPlanExecutionError,
    DeferredPlanExecutor,
    DeferredPlanOutcome,
    DeferredPlanReceipt,
    DeferredPlanStep,
)
from .executor import (
    DeferredExecutionError,
    DeferredExecutor,
    DeferredInvocation,
    ExecutionOutcome,
    ExecutionReceipt,
    FailureReceipt,
)

__all__ = [
    "CapabilityRegistry",
    "CapabilitySpec",
    "DEFERRED_165_SPECS",
    "DeferredExecutionError",
    "DeferredPlan",
    "DeferredPlanExecutionError",
    "DeferredPlanExecutor",
    "DeferredPlanOutcome",
    "DeferredPlanReceipt",
    "DeferredPlanStep",
    "DeferredExecutor",
    "DeferredInvocation",
    "EvidenceReceipt",
    "ExecutionOutcome",
    "ExecutionReceipt",
    "FailureReceipt",
    "build_registry",
    "volume_ids",
]
