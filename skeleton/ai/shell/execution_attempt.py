"""Compatibility shim — re-exports `skeleton.shells.ai.execution_attempt`.

This shim exists so callers of `skeleton.ai.shell.execution_attempt` keep working while `skeleton.shells.ai.execution_attempt` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.execution_attempt import (
    ExecutionAttemptState,
    TERMINAL_ATTEMPT_STATES,
    ExecutionAttemptRecovery,
    AIExecutionAttempt,
    StoredExecutionAttempt,
    ExecutionAttemptSessionHead,
    ExecutionAttemptConflict,
    AIExecutionAttemptStore,
    AttemptTrackingExecutionBackend,
)

__all__ = ['ExecutionAttemptState', 'TERMINAL_ATTEMPT_STATES', 'ExecutionAttemptRecovery', 'AIExecutionAttempt', 'StoredExecutionAttempt', 'ExecutionAttemptSessionHead', 'ExecutionAttemptConflict', 'AIExecutionAttemptStore', 'AttemptTrackingExecutionBackend']
