"""Compatibility shim — re-exports `skeleton.shells.ai.durable_checkpoint`.

This shim exists so callers of `skeleton.ai.shell.durable_checkpoint` keep working while `skeleton.shells.ai.durable_checkpoint` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpoint,
    SignedDurableChainCheckpoint,
    DurableCheckpointVerification,
    DurableCheckpointError,
    DurableCheckpointLookupIndex,
    DurableCheckpointIndexState,
    DurableCheckpointIndexHealth,
    DurableChainCheckpointStore,
)

__all__ = ['CheckpointableEvidenceChain', 'DurableChainCheckpoint', 'SignedDurableChainCheckpoint', 'DurableCheckpointVerification', 'DurableCheckpointError', 'DurableCheckpointLookupIndex', 'DurableCheckpointIndexState', 'DurableCheckpointIndexHealth', 'DurableChainCheckpointStore']
