"""Compatibility shim — re-exports `skeleton.shells.ai.provider_router`.

This shim exists so callers of `skeleton.ai.shell.provider_router` keep working while `skeleton.shells.ai.provider_router` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.provider_router import (
    ProviderRoute,
    AIProviderRouter,
)

__all__ = ['ProviderRoute', 'AIProviderRouter']
