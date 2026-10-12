"""Compatibility shim — re-exports `skeleton.shells.ai.model_circuit`.

This shim exists so callers of `skeleton.ai.shell.model_circuit` keep working while `skeleton.shells.ai.model_circuit` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.model_circuit import (
    ModelCircuitState,
    ModelCircuitPolicy,
    ModelCircuitSnapshot,
    ModelCircuitOpen,
    ModelCircuitRegistry,
)

__all__ = ['ModelCircuitState', 'ModelCircuitPolicy', 'ModelCircuitSnapshot', 'ModelCircuitOpen', 'ModelCircuitRegistry']
