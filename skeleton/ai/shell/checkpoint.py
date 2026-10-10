"""Compatibility shim — re-exports `skeleton.shells.ai.checkpoint`.

This shim exists so callers of `skeleton.ai.shell.checkpoint` keep working while `skeleton.shells.ai.checkpoint` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.checkpoint import (
    AISessionCheckpoint,
)

__all__ = ['AISessionCheckpoint']
