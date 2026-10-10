"""Compatibility shim — re-exports `skeleton.shells.ai.session_evidence`.

This shim exists so callers of `skeleton.ai.shell.session_evidence` keep working while `skeleton.shells.ai.session_evidence` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.session_evidence import (
    SessionReceiptEvidence,
    SessionExecutionEvidence,
    StoredSessionEvidence,
    SessionEvidenceConflict,
    SessionEvidenceStore,
)

__all__ = ['SessionReceiptEvidence', 'SessionExecutionEvidence', 'StoredSessionEvidence', 'SessionEvidenceConflict', 'SessionEvidenceStore']
