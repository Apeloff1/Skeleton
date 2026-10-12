"""Compatibility shim — re-exports `skeleton.shells.ai.stale_guard`.

This shim exists so callers of `skeleton.ai.shell.stale_guard` keep working while `skeleton.shells.ai.stale_guard` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.stale_guard import (
    StalenessKind,
    StalenessFinding,
    StalenessReport,
    PlanPin,
    AIPlanStaleGuard,
)

__all__ = ['StalenessKind', 'StalenessFinding', 'StalenessReport', 'PlanPin', 'AIPlanStaleGuard']
