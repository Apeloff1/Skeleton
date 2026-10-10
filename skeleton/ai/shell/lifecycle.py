"""Compatibility shim — re-exports `skeleton.shells.ai.lifecycle`.

This shim exists so callers of `skeleton.ai.shell.lifecycle` keep working while `skeleton.shells.ai.lifecycle` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.lifecycle import (
    AIServicePhase,
    AIServiceTransition,
    AIServiceState,
)

__all__ = ['AIServicePhase', 'AIServiceTransition', 'AIServiceState']
