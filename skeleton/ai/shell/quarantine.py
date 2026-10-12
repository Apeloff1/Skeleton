"""Compatibility shim — re-exports `skeleton.shells.ai.quarantine`.

This shim exists so callers of `skeleton.ai.shell.quarantine` keep working while `skeleton.shells.ai.quarantine` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.quarantine import (
    QuarantineTarget,
    QuarantineRecord,
    AIQuarantine,
)

__all__ = ['QuarantineTarget', 'QuarantineRecord', 'AIQuarantine']
