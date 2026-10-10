"""Compatibility shim — re-exports `skeleton.shells.ai.durable_merkle`.

This shim exists so callers of `skeleton.ai.shell.durable_merkle` keep working while `skeleton.shells.ai.durable_merkle` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_merkle import (
    MERKLE_ALGORITHM,
    MERKLE_CHECKPOINT_ARTIFACT,
    LEAF_DOMAIN,
    NODE_DOMAIN,
    EMPTY_DOMAIN,
    DurableMerkleChainKind,
    DurableMerkleSide,
    MerkleCheckpointChain,
    DurableMerkleLeaf,
    DurableMerkleProofStep,
    DurableMerkleCheckpoint,
    SignedDurableMerkleCheckpoint,
    DurableMerkleProof,
    DurableMerkleVerification,
    DurableMerkleError,
    DurableMerkleAuthority,
)

__all__ = ['MERKLE_ALGORITHM', 'MERKLE_CHECKPOINT_ARTIFACT', 'LEAF_DOMAIN', 'NODE_DOMAIN', 'EMPTY_DOMAIN', 'DurableMerkleChainKind', 'DurableMerkleSide', 'MerkleCheckpointChain', 'DurableMerkleLeaf', 'DurableMerkleProofStep', 'DurableMerkleCheckpoint', 'SignedDurableMerkleCheckpoint', 'DurableMerkleProof', 'DurableMerkleVerification', 'DurableMerkleError', 'DurableMerkleAuthority']
