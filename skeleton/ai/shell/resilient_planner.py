"""Compatibility shim — re-exports `skeleton.shells.ai.resilient_planner`.

This shim exists so callers of `skeleton.ai.shell.resilient_planner` keep working while `skeleton.shells.ai.resilient_planner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.resilient_planner import (
    PlannerAttempt,
    ResilientPlanningResult,
    ResilientAIPlanner,
)

__all__ = ['PlannerAttempt', 'ResilientPlanningResult', 'ResilientAIPlanner']
