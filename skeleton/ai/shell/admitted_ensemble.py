"""Compatibility shim — re-exports `skeleton.shells.ai.admitted_ensemble`.

This shim exists so callers of `skeleton.ai.shell.admitted_ensemble` keep working while `skeleton.shells.ai.admitted_ensemble` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.admitted_ensemble import (
    AdmittedEnsembleResult,
    AdmittedEnsembleAIPlanner,
)

__all__ = ['AdmittedEnsembleResult', 'AdmittedEnsembleAIPlanner']
