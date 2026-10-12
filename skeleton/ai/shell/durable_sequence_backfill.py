"""Compatibility shim — re-exports `skeleton.shells.ai.durable_sequence_backfill`.

This shim exists so callers of `skeleton.ai.shell.durable_sequence_backfill` keep working while `skeleton.shells.ai.durable_sequence_backfill` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_sequence_backfill import (
    GENESIS_HASH,
    DurableSequenceBackfillPolicy,
    DurableSequenceBackfillCursor,
    DurableSequenceBackfillState,
    DurableSequenceBackfillStep,
    DurableSequenceBackfillChainReport,
    DurableSequenceBackfillFleetReport,
    DurableSequenceBackfillError,
    DurableSequenceBackfillOperator,
)

__all__ = ['GENESIS_HASH', 'DurableSequenceBackfillPolicy', 'DurableSequenceBackfillCursor', 'DurableSequenceBackfillState', 'DurableSequenceBackfillStep', 'DurableSequenceBackfillChainReport', 'DurableSequenceBackfillFleetReport', 'DurableSequenceBackfillError', 'DurableSequenceBackfillOperator']
