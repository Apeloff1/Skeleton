"""Compatibility shim — re-exports `skeleton.shells.ai.budget`.

This shim exists so callers of `skeleton.ai.shell.budget` keep working while `skeleton.shells.ai.budget` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.budget import (
    AIBudgetLimit,
    AIBudgetUsage,
    AIBudgetExceeded,
    AIBudget,
)

__all__ = ['AIBudgetLimit', 'AIBudgetUsage', 'AIBudgetExceeded', 'AIBudget']
