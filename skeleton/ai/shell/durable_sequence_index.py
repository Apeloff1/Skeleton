"""Compatibility shim — re-exports `skeleton.shells.ai.durable_sequence_index`.

This shim exists so callers of `skeleton.ai.shell.durable_sequence_index` keep working while `skeleton.shells.ai.durable_sequence_index` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexState,
    DurableSequenceIndexPolicy,
    DurableSequenceIndexFinding,
    DurableSequenceIndexChainReport,
    DurableSequenceIndexFleetReport,
    DurableSequenceIndexError,
    DurableSequenceIndexOperator,
)

__all__ = ['DurableSequenceIndexState', 'DurableSequenceIndexPolicy', 'DurableSequenceIndexFinding', 'DurableSequenceIndexChainReport', 'DurableSequenceIndexFleetReport', 'DurableSequenceIndexError', 'DurableSequenceIndexOperator']
