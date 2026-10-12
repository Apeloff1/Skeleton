"""Compatibility shim — re-exports `skeleton.shells.ai.ensemble_planner`.

This shim exists so callers of `skeleton.ai.shell.ensemble_planner` keep working while `skeleton.shells.ai.ensemble_planner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.ensemble_planner import (
    EnsembleMember,
    EnsemblePolicy,
    EnsembleAttempt,
    EnsemblePlanningResult,
    EnsembleAIPlanner,
)

__all__ = ['EnsembleMember', 'EnsemblePolicy', 'EnsembleAttempt', 'EnsemblePlanningResult', 'EnsembleAIPlanner']
