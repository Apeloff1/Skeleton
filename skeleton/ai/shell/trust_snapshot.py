"""Compatibility shim — re-exports `skeleton.shells.ai.trust_snapshot`.

This shim exists so callers of `skeleton.ai.shell.trust_snapshot` keep working while `skeleton.shells.ai.trust_snapshot` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.trust_snapshot import (
    AITrustSnapshot,
    SignedAITrustSnapshot,
    AITrustSnapshotBuilder,
)

__all__ = ['AITrustSnapshot', 'SignedAITrustSnapshot', 'AITrustSnapshotBuilder']
