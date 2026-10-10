"""Compatibility shim — re-exports `skeleton.shells.ai.session_journal`.

This shim exists so callers of `skeleton.ai.shell.session_journal` keep working while `skeleton.shells.ai.session_journal` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.session_journal import (
    SessionJournalEvent,
    SessionJournalEvidence,
)

__all__ = ['SessionJournalEvent', 'SessionJournalEvidence']
