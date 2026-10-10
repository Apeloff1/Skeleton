"""Compatibility shim — re-exports `skeleton.shells.ai.approval_quorum`.

This shim exists so callers of `skeleton.ai.shell.approval_quorum` keep working while `skeleton.shells.ai.approval_quorum` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.approval_quorum import (
    QuorumVoteDecision,
    QuorumApprovalState,
    QuorumApprovalPolicy,
    QuorumVote,
    QuorumApproval,
    StoredQuorumApproval,
    QuorumApprovalError,
    AIApprovalQuorumStore,
)

__all__ = ['QuorumVoteDecision', 'QuorumApprovalState', 'QuorumApprovalPolicy', 'QuorumVote', 'QuorumApproval', 'StoredQuorumApproval', 'QuorumApprovalError', 'AIApprovalQuorumStore']
