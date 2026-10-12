"""Compatibility shim — re-exports `skeleton.shells.ai.planner`.

This shim exists so callers of `skeleton.ai.shell.planner` keep working while `skeleton.shells.ai.planner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.planner import (
    PlanningResult,
    AIPlanner,
)

__all__ = ['PlanningResult', 'AIPlanner']
