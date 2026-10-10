"""Compatibility shim — re-exports `skeleton.shells.ai.snapshot`.

This shim exists so callers of `skeleton.ai.shell.snapshot` keep working while `skeleton.shells.ai.snapshot` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.snapshot import (
    AIShellSnapshot,
    AIShellSnapshotter,
)

__all__ = ['AIShellSnapshot', 'AIShellSnapshotter']
