"""Compatibility shim — re-exports `skeleton.shells.ai.consensus`.

This shim exists so callers of `skeleton.ai.shell.consensus` keep working while `skeleton.shells.ai.consensus` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.consensus import (
    proposal_shape,
    proposal_shape_digest,
    ConsensusGroup,
    ConsensusReport,
    ProposalConsensus,
)

__all__ = ['proposal_shape', 'proposal_shape_digest', 'ConsensusGroup', 'ConsensusReport', 'ProposalConsensus']
