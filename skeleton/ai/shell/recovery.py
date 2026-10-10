"""Compatibility shim — re-exports `skeleton.shells.ai.recovery`.

This shim exists so callers of `skeleton.ai.shell.recovery` keep working while `skeleton.shells.ai.recovery` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.recovery import (
    RecoveryAction,
    AIRecoveryReport,
    AIRecoveryManager,
)

__all__ = ['RecoveryAction', 'AIRecoveryReport', 'AIRecoveryManager']
