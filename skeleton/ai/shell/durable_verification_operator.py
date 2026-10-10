"""Compatibility shim — re-exports `skeleton.shells.ai.durable_verification_operator`.

This shim exists so callers of `skeleton.ai.shell.durable_verification_operator` keep working while `skeleton.shells.ai.durable_verification_operator` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperatorState,
    DurableVerificationOperatorPolicy,
    DurableVerificationOperatorChainReport,
    DurableVerificationOperatorReport,
    DurableVerificationRefreshReport,
    DurableVerificationOperatorError,
    DurableVerificationOperator,
)

__all__ = ['DurableVerificationOperatorState', 'DurableVerificationOperatorPolicy', 'DurableVerificationOperatorChainReport', 'DurableVerificationOperatorReport', 'DurableVerificationRefreshReport', 'DurableVerificationOperatorError', 'DurableVerificationOperator']
