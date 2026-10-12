"""Compatibility shim — re-exports `skeleton.shells.ai.store_protocol`.

This shim exists so callers of `skeleton.ai.shell.store_protocol` keep working while `skeleton.shells.ai.store_protocol` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.store_protocol import (
    VersionedStateBackend,
    RecordListingBackend,
    FencedLeaseBackend,
    DistributedAIBackend,
)

__all__ = ['VersionedStateBackend', 'RecordListingBackend', 'FencedLeaseBackend', 'DistributedAIBackend']
