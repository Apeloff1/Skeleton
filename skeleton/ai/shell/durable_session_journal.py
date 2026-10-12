"""Compatibility shim — re-exports `skeleton.shells.ai.durable_session_journal`.

This shim exists so callers of `skeleton.ai.shell.durable_session_journal` keep working while `skeleton.shells.ai.durable_session_journal` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalManifest,
    DurableSessionJournalHead,
    StoredDurableSessionJournal,
    DurableSessionJournalCommit,
    DurableSessionJournalConflict,
    DurableSessionJournalCorruption,
    DurableSessionJournalStore,
)

__all__ = ['DurableSessionJournalManifest', 'DurableSessionJournalHead', 'StoredDurableSessionJournal', 'DurableSessionJournalCommit', 'DurableSessionJournalConflict', 'DurableSessionJournalCorruption', 'DurableSessionJournalStore']
