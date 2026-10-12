"""Compatibility shim — re-exports `skeleton.shells.ai.finalization_state`.

This shim exists so callers of `skeleton.ai.shell.finalization_state` keep working while `skeleton.shells.ai.finalization_state` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.finalization_state import (
    FinalizationPhase,
    FinalizationRecovery,
    AIExecutionFinalization,
    StoredExecutionFinalization,
    ExecutionFinalizationConflict,
    AIExecutionFinalizationStore,
)

__all__ = ['FinalizationPhase', 'FinalizationRecovery', 'AIExecutionFinalization', 'StoredExecutionFinalization', 'ExecutionFinalizationConflict', 'AIExecutionFinalizationStore']
