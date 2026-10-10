"""Compatibility shim — re-exports `skeleton.shells.ai.session`.

This shim exists so callers of `skeleton.ai.shell.session` keep working while `skeleton.shells.ai.session` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.session import (
    AISessionPhase,
    AISessionTransition,
    AIShellSession,
)

__all__ = ['AISessionPhase', 'AISessionTransition', 'AIShellSession']
