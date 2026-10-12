"""Compatibility shim — re-exports `skeleton.shells.ai.recovery_store`.

This shim exists so callers of `skeleton.ai.shell.recovery_store` keep working while `skeleton.shells.ai.recovery_store` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.recovery_store import (
    RecoveryCheckpointRecord,
    RecoveryCheckpointHead,
    StoredRecoveryCheckpoint,
    RecoveryCheckpointCommit,
    RecoveryCheckpointConflict,
    AIRecoveryCheckpointStore,
)

__all__ = ['RecoveryCheckpointRecord', 'RecoveryCheckpointHead', 'StoredRecoveryCheckpoint', 'RecoveryCheckpointCommit', 'RecoveryCheckpointConflict', 'AIRecoveryCheckpointStore']
