"""Compatibility shim — re-exports `skeleton.shells.ai.session_integrity`.

This shim exists so callers of `skeleton.ai.shell.session_integrity` keep working while `skeleton.shells.ai.session_integrity` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.session_integrity import (
    JournalInclusionResult,
    ReceiptInclusionResult,
    SessionEvidenceIntegrityReport,
    SessionEvidenceIntegrityError,
    SessionEvidenceIntegrityVerifier,
)

__all__ = ['JournalInclusionResult', 'ReceiptInclusionResult', 'SessionEvidenceIntegrityReport', 'SessionEvidenceIntegrityError', 'SessionEvidenceIntegrityVerifier']
