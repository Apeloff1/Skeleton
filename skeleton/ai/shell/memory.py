"""Compatibility shim — re-exports `skeleton.shells.ai.memory`.

This shim exists so callers of `skeleton.ai.shell.memory` keep working while `skeleton.shells.ai.memory` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.memory import (
    OutcomeMemory,
    AIOutcomeMemory,
)

__all__ = ['OutcomeMemory', 'AIOutcomeMemory']
