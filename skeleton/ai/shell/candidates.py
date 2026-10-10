"""Compatibility shim — re-exports `skeleton.shells.ai.candidates`.

This shim exists so callers of `skeleton.ai.shell.candidates` keep working while `skeleton.shells.ai.candidates` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.candidates import (
    CandidateEvaluation,
    CandidateSelection,
    CandidateSelector,
)

__all__ = ['CandidateEvaluation', 'CandidateSelection', 'CandidateSelector']
