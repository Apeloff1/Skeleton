"""Compatibility shim — re-exports `skeleton.shells.ai.durable_checkpoint_repair`.

This shim exists so callers of `skeleton.ai.shell.durable_checkpoint_repair` keep working while `skeleton.shells.ai.durable_checkpoint_repair` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_checkpoint_repair import (
    CheckpointIndexRepairAction,
    CheckpointIndexRepairState,
    CheckpointIndexRepairPolicy,
    CheckpointIndexRepairPlan,
    CheckpointIndexRepairResult,
    CheckpointIndexRepairBatchReport,
    CheckpointIndexRepairError,
    DurableCheckpointIndexRepairCoordinator,
)

__all__ = ['CheckpointIndexRepairAction', 'CheckpointIndexRepairState', 'CheckpointIndexRepairPolicy', 'CheckpointIndexRepairPlan', 'CheckpointIndexRepairResult', 'CheckpointIndexRepairBatchReport', 'CheckpointIndexRepairError', 'DurableCheckpointIndexRepairCoordinator']
