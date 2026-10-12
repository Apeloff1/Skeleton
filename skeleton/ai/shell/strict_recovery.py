"""Compatibility shim — re-exports `skeleton.shells.ai.strict_recovery`.

This shim exists so callers of `skeleton.ai.shell.strict_recovery` keep working while `skeleton.shells.ai.strict_recovery` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.strict_recovery import (
    StrictRecoveryReport,
    StrictAIRecoveryManager,
)

__all__ = ['StrictRecoveryReport', 'StrictAIRecoveryManager']
