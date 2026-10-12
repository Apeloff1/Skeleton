"""Compatibility shim — re-exports `skeleton.shells.ai.release_registry`.

This shim exists so callers of `skeleton.ai.shell.release_registry` keep working while `skeleton.shells.ai.release_registry` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.release_registry import (
    RegisteredRelease,
    ReleaseRegistryConflict,
    AIReleaseRegistry,
)

__all__ = ['RegisteredRelease', 'ReleaseRegistryConflict', 'AIReleaseRegistry']
