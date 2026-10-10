"""Compatibility shim — re-exports `skeleton.shells.ai.manifest`.

This shim exists so callers of `skeleton.ai.shell.manifest` keep working while `skeleton.shells.ai.manifest` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.manifest import (
    AI_SHELL_MANIFEST_VERSION,
    AIToolManifest,
    build_manifest,
)

__all__ = ['AI_SHELL_MANIFEST_VERSION', 'AIToolManifest', 'build_manifest']
