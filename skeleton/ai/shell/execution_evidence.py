"""Compatibility shim — re-exports `skeleton.shells.ai.execution_evidence`.

This shim exists so callers of `skeleton.ai.shell.execution_evidence` keep working while `skeleton.shells.ai.execution_evidence` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.execution_evidence import (
    AIExecutionEvidence,
    SignedAIExecutionEvidence,
    AIExecutionEvidenceBuilder,
    AIExecutionEvidenceStore,
)

__all__ = ['AIExecutionEvidence', 'SignedAIExecutionEvidence', 'AIExecutionEvidenceBuilder', 'AIExecutionEvidenceStore']
