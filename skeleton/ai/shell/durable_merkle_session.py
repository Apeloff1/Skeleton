"""Compatibility shim — re-exports `skeleton.shells.ai.durable_merkle_session`.

This shim exists so callers of `skeleton.ai.shell.durable_merkle_session` keep working while `skeleton.shells.ai.durable_merkle_session` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleProofBundle,
    DurableSessionMerkleVerification,
    DurableSessionMerkleError,
    DurableSessionMerkleAuthority,
)

__all__ = ['DurableSessionMerkleProofBundle', 'DurableSessionMerkleVerification', 'DurableSessionMerkleError', 'DurableSessionMerkleAuthority']
