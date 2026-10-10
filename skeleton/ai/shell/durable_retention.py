"""Compatibility shim — re-exports `skeleton.shells.ai.durable_retention`.

This shim exists so callers of `skeleton.ai.shell.durable_retention` keep working while `skeleton.shells.ai.durable_retention` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_retention import (
    DurableRetentionState,
    DurableRetentionPolicy,
    ProtectedHistoricalRoot,
    DurableRetentionPlan,
    DurableRetentionError,
    DurableRetentionPlanner,
)

__all__ = ['DurableRetentionState', 'DurableRetentionPolicy', 'ProtectedHistoricalRoot', 'DurableRetentionPlan', 'DurableRetentionError', 'DurableRetentionPlanner']
