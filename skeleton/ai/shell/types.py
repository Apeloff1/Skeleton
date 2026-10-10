"""Compatibility shim — re-exports `skeleton.shells.ai.types`.

This shim exists so callers of `skeleton.ai.shell.types` keep working while `skeleton.shells.ai.types` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.types import (
    IntentKind,
    IntentConstraint,
    VerificationCriterion,
    AIIntent,
    AIAction,
    AIPlanProposal,
)

__all__ = ['IntentKind', 'IntentConstraint', 'VerificationCriterion', 'AIIntent', 'AIAction', 'AIPlanProposal']
