"""Compatibility shim — re-exports `skeleton.shells.ai.assurance`.

This shim exists so callers of `skeleton.ai.shell.assurance` keep working while `skeleton.shells.ai.assurance` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.assurance import (
    AssuranceLevel,
    AIExecutionAssurancePolicy,
    AssuranceDecision,
    AIExecutionAssuranceInspector,
)

__all__ = ['AssuranceLevel', 'AIExecutionAssurancePolicy', 'AssuranceDecision', 'AIExecutionAssuranceInspector']
