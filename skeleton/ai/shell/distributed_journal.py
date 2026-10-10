"""Compatibility shim — re-exports `skeleton.shells.ai.distributed_journal`.

This shim exists so callers of `skeleton.ai.shell.distributed_journal` keep working while `skeleton.shells.ai.distributed_journal` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.distributed_journal import (
    GENESIS_HASH,
    DistributedJournalHead,
    DistributedJournalSequenceIndex,
    DistributedJournalIndexHealth,
    DistributedJournalConflict,
    DistributedJournalCorruption,
    DistributedAIDecisionJournal,
)

__all__ = ['GENESIS_HASH', 'DistributedJournalHead', 'DistributedJournalSequenceIndex', 'DistributedJournalIndexHealth', 'DistributedJournalConflict', 'DistributedJournalCorruption', 'DistributedAIDecisionJournal']
