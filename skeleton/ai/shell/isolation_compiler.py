"""Compatibility shim — re-exports `skeleton.shells.ai.isolation_compiler`.

This shim exists so callers of `skeleton.ai.shell.isolation_compiler` keep working while `skeleton.shells.ai.isolation_compiler` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.isolation_compiler import (
    AIIsolationDecision,
    AIIsolationCompiler,
)

__all__ = ['AIIsolationDecision', 'AIIsolationCompiler']
