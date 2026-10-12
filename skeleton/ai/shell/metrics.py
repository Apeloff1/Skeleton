"""Compatibility shim — re-exports `skeleton.shells.ai.metrics`.

This shim exists so callers of `skeleton.ai.shell.metrics` keep working while `skeleton.shells.ai.metrics` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.metrics import (
    AICommandMetrics,
    AIShellMetrics,
)

__all__ = ['AICommandMetrics', 'AIShellMetrics']
