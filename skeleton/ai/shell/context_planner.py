"""Compatibility shim — re-exports `skeleton.shells.ai.context_planner`.

This shim exists so callers of `skeleton.ai.shell.context_planner` keep working while `skeleton.shells.ai.context_planner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.context_planner import (
    ContextPlanningResult,
    ContextAwareAIPlanner,
)

__all__ = ['ContextPlanningResult', 'ContextAwareAIPlanner']
