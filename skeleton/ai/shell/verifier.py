"""Compatibility shim — re-exports `skeleton.shells.ai.verifier`.

This shim exists so callers of `skeleton.ai.shell.verifier` keep working while `skeleton.shells.ai.verifier` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.verifier import (
    VerificationState,
    CriterionResult,
    VerificationReport,
    PlanVerifier,
)

__all__ = ['VerificationState', 'CriterionResult', 'VerificationReport', 'PlanVerifier']
