"""Compatibility shim — re-exports `skeleton.shells.ai.execution_fence`.

This shim exists so callers of `skeleton.ai.shell.execution_fence` keep working while `skeleton.shells.ai.execution_fence` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.execution_fence import (
    AIExecutionFencePolicy,
    AIExecutionFenceBinding,
    AIExecutionFence,
    AIExecutionFenceError,
    AIExecutionFenceManager,
)

__all__ = ['AIExecutionFencePolicy', 'AIExecutionFenceBinding', 'AIExecutionFence', 'AIExecutionFenceError', 'AIExecutionFenceManager']
