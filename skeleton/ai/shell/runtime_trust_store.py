"""Compatibility shim — re-exports `skeleton.shells.ai.runtime_trust_store`.

This shim exists so callers of `skeleton.ai.shell.runtime_trust_store` keep working while `skeleton.shells.ai.runtime_trust_store` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.runtime_trust_store import (
    RuntimeTrustPin,
    SignedRuntimeTrustPin,
    RuntimeTrustPinVerification,
    RuntimeTrustPinConflict,
    RuntimeTrustPinStore,
)

__all__ = ['RuntimeTrustPin', 'SignedRuntimeTrustPin', 'RuntimeTrustPinVerification', 'RuntimeTrustPinConflict', 'RuntimeTrustPinStore']
