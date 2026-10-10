"""Compatibility shim — re-exports `skeleton.shells.ai.durable_archive`.

This shim exists so callers of `skeleton.ai.shell.durable_archive` keep working while `skeleton.shells.ai.durable_archive` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_archive import (
    DurableArchiveEntry,
    DurableArchiveManifest,
    SignedDurableArchiveManifest,
    DurableArchiveVerification,
    DurableArchiveError,
    DurableArchiveManifestBuilder,
)

__all__ = ['DurableArchiveEntry', 'DurableArchiveManifest', 'SignedDurableArchiveManifest', 'DurableArchiveVerification', 'DurableArchiveError', 'DurableArchiveManifestBuilder']
