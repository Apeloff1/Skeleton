"""Compatibility shim — re-exports `skeleton.shells.ai.durable_proof_window`.

This shim exists so callers of `skeleton.ai.shell.durable_proof_window` keep working while `skeleton.shells.ai.durable_proof_window` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_proof_window import (
    PROOF_ARTIFACT_TYPE,
    ProofWindowChain,
    DurableHistoricalProofWindow,
    SignedDurableHistoricalProofWindow,
    DurableHistoricalProofVerification,
    DurableHistoricalProofError,
    DurableHistoricalProofAuthority,
    DurableHistoricalProofIndex,
    DurableHistoricalProofStore,
)

__all__ = ['PROOF_ARTIFACT_TYPE', 'ProofWindowChain', 'DurableHistoricalProofWindow', 'SignedDurableHistoricalProofWindow', 'DurableHistoricalProofVerification', 'DurableHistoricalProofError', 'DurableHistoricalProofAuthority', 'DurableHistoricalProofIndex', 'DurableHistoricalProofStore']
