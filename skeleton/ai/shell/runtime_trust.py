"""Compatibility shim — re-exports `skeleton.shells.ai.runtime_trust`.

This shim exists so callers of `skeleton.ai.shell.runtime_trust` keep working while `skeleton.shells.ai.runtime_trust` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.runtime_trust import (
    RuntimeTrustSurface,
    RuntimeModelBinding,
    RuntimeTrustEpoch,
    DurableRuntimeTrustPinStore,
    RuntimeTrustReport,
    AIRuntimeTrustGuard,
)

__all__ = ['RuntimeTrustSurface', 'RuntimeModelBinding', 'RuntimeTrustEpoch', 'DurableRuntimeTrustPinStore', 'RuntimeTrustReport', 'AIRuntimeTrustGuard']
