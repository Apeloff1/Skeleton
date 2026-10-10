"""Compatibility shim — re-exports `skeleton.shells.ai.durable_archive_store`.

This shim exists so callers of `skeleton.ai.shell.durable_archive_store` keep working while `skeleton.shells.ai.durable_archive_store` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_archive_store import (
    GENESIS_HASH,
    DurableArchivedNodeType,
    DurableArchivedNode,
    DurableArchiveRootReplica,
    DurableArchiveRootIndex,
    DurableArchiveSequenceIndex,
    DurableArchiveSequenceIndexHealth,
    DurableArchiveRootResolution,
    DurableArchiveHead,
    StoredDurableArchive,
    DurableArchiveStoreReport,
    DurableArchiveStoreError,
    DurableArchiveIndexState,
    DurableArchiveIndexHealth,
    DurableArchiveRepository,
    ArchiveBackedHistoricalChain,
)

__all__ = ['GENESIS_HASH', 'DurableArchivedNodeType', 'DurableArchivedNode', 'DurableArchiveRootReplica', 'DurableArchiveRootIndex', 'DurableArchiveSequenceIndex', 'DurableArchiveSequenceIndexHealth', 'DurableArchiveRootResolution', 'DurableArchiveHead', 'StoredDurableArchive', 'DurableArchiveStoreReport', 'DurableArchiveStoreError', 'DurableArchiveIndexState', 'DurableArchiveIndexHealth', 'DurableArchiveRepository', 'ArchiveBackedHistoricalChain']
