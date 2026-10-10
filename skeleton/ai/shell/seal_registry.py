"""Compatibility shim — re-exports `skeleton.shells.ai.seal_registry`.

This shim exists so callers of `skeleton.ai.shell.seal_registry` keep working while `skeleton.shells.ai.seal_registry` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.seal_registry import (
    SealUse,
    SealReplay,
    ExecutionSealRegistry,
)

__all__ = ['SealUse', 'SealReplay', 'ExecutionSealRegistry']
