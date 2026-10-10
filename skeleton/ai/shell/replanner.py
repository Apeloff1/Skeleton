"""Compatibility shim — re-exports `skeleton.shells.ai.replanner`.

This shim exists so callers of `skeleton.ai.shell.replanner` keep working while `skeleton.shells.ai.replanner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.replanner import (
    ReplanStop,
    ReplanRound,
    ReplanReport,
    BoundedReplanner,
)

__all__ = ['ReplanStop', 'ReplanRound', 'ReplanReport', 'BoundedReplanner']
