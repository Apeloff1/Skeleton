"""Compatibility shim — re-exports `skeleton.shells.ai.durable_verification_cursor`.

This shim exists so callers of `skeleton.ai.shell.durable_verification_cursor` keep working while `skeleton.shells.ai.durable_verification_cursor` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_verification_cursor import (
    IncrementallyVerifiableChain,
    DurableVerificationMode,
    DurableVerificationStatus,
    DurableVerificationPolicy,
    DurableVerificationCursor,
    SignedDurableVerificationCursor,
    DurableVerificationCursorHead,
    StoredDurableVerificationCursor,
    DurableVerificationReport,
    DurableVerificationResult,
    DurableVerificationCursorError,
    DurableVerificationCursorStore,
    DurableIncrementalVerifier,
)

__all__ = ['IncrementallyVerifiableChain', 'DurableVerificationMode', 'DurableVerificationStatus', 'DurableVerificationPolicy', 'DurableVerificationCursor', 'SignedDurableVerificationCursor', 'DurableVerificationCursorHead', 'StoredDurableVerificationCursor', 'DurableVerificationReport', 'DurableVerificationResult', 'DurableVerificationCursorError', 'DurableVerificationCursorStore', 'DurableIncrementalVerifier']
