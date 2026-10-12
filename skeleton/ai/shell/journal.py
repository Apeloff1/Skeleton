"""Compatibility shim — re-exports `skeleton.shells.ai.journal`.

This shim exists so callers of `skeleton.ai.shell.journal` keep working while `skeleton.shells.ai.journal` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)

__all__ = ['AIDecisionEvent', 'AIDecisionJournal']
