"""Compatibility shim — re-exports `skeleton.shells.ai.durable_session_commit`.

This shim exists so callers of `skeleton.ai.shell.durable_session_commit` keep working while `skeleton.shells.ai.durable_session_commit` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_session_commit import (
    finalization_evidence_dict,
    finalization_evidence_digest,
    DurableSessionCommitPolicy,
    DurableSessionCommit,
    SignedDurableSessionCommit,
    DurableSessionCommitHead,
    StoredDurableSessionCommit,
    DurableSessionCommitPublication,
    DurableSessionCommitConflict,
    DurableSessionCommitCorruption,
    DurableSessionCommitBuilder,
    DurableSessionCommitStore,
)

__all__ = ['finalization_evidence_dict', 'finalization_evidence_digest', 'DurableSessionCommitPolicy', 'DurableSessionCommit', 'SignedDurableSessionCommit', 'DurableSessionCommitHead', 'StoredDurableSessionCommit', 'DurableSessionCommitPublication', 'DurableSessionCommitConflict', 'DurableSessionCommitCorruption', 'DurableSessionCommitBuilder', 'DurableSessionCommitStore']
