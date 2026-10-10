"""Compatibility shim — re-exports `skeleton.shells.ai.durable_orphan_scan`.

This shim exists so callers of `skeleton.ai.shell.durable_orphan_scan` keep working while `skeleton.shells.ai.durable_orphan_scan` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_orphan_scan import (
    GENESIS_HASH,
    DurableOrphanNodeKind,
    DurableOrphanRecordState,
    DurableOrphanScanPolicy,
    DurableOrphanNodeRecord,
    DurableOrphanScanReport,
    DurableOrphanScanError,
    DurableOrphanScanner,
)

__all__ = ['GENESIS_HASH', 'DurableOrphanNodeKind', 'DurableOrphanRecordState', 'DurableOrphanScanPolicy', 'DurableOrphanNodeRecord', 'DurableOrphanScanReport', 'DurableOrphanScanError', 'DurableOrphanScanner']
