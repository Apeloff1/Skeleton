"""Compatibility shim — re-exports `skeleton.shells.ai.execution_seal`.

This shim exists so callers of `skeleton.ai.shell.execution_seal` keep working while `skeleton.shells.ai.execution_seal` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.execution_seal import (
    ExecutionSeal,
    ExecutionSealError,
    ExecutionSealAuthority,
)

__all__ = ['ExecutionSeal', 'ExecutionSealError', 'ExecutionSealAuthority']
