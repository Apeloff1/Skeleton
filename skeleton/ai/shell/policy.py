"""Compatibility shim — re-exports `skeleton.shells.ai.policy`.

This shim exists so callers of `skeleton.ai.shell.policy` keep working while `skeleton.shells.ai.policy` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.policy import (
    AutonomyMode,
    AIPolicyDecision,
    AIShellPolicy,
)

__all__ = ['AutonomyMode', 'AIPolicyDecision', 'AIShellPolicy']
