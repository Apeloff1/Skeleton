"""Compatibility shim — re-exports `skeleton.shells.ai.robust_consensus`.

This shim exists so callers of `skeleton.ai.shell.robust_consensus` keep working while `skeleton.shells.ai.robust_consensus` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.robust_consensus import (
    ConsensusPolicy,
    RobustConsensusGroup,
    RobustConsensusReport,
    RobustProposalConsensus,
)

__all__ = ['ConsensusPolicy', 'RobustConsensusGroup', 'RobustConsensusReport', 'RobustProposalConsensus']
