"""Compatibility shim — re-exports `skeleton.shells.ai.resource_profile`.

This shim exists so callers of `skeleton.ai.shell.resource_profile` keep working while `skeleton.shells.ai.resource_profile` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.resource_profile import (
    AIResourceProfile,
    AIResourcePolicy,
    AIResourceDecision,
    AIResourceCompiler,
)

__all__ = ['AIResourceProfile', 'AIResourcePolicy', 'AIResourceDecision', 'AIResourceCompiler']
