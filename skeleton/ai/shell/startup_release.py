"""Compatibility shim — re-exports `skeleton.shells.ai.startup_release`.

This shim exists so callers of `skeleton.ai.shell.startup_release` keep working while `skeleton.shells.ai.startup_release` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.startup_release import (
    RuntimeReleaseExpectation,
    StartupReleaseReport,
    AIStartupReleaseGuard,
)

__all__ = ['RuntimeReleaseExpectation', 'StartupReleaseReport', 'AIStartupReleaseGuard']
