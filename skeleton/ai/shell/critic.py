"""Compatibility shim — re-exports `skeleton.shells.ai.critic`.

This shim exists so callers of `skeleton.ai.shell.critic` keep working while `skeleton.shells.ai.critic` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.critic import (
    CritiqueSeverity,
    CritiqueFinding,
    CritiqueReport,
    AIPlanCritic,
)

__all__ = ['CritiqueSeverity', 'CritiqueFinding', 'CritiqueReport', 'AIPlanCritic']
