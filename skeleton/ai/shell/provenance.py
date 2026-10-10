"""Compatibility shim — re-exports `skeleton.shells.ai.provenance`.

This shim exists so callers of `skeleton.ai.shell.provenance` keep working while `skeleton.shells.ai.provenance` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.provenance import (
    AIDecisionProvenance,
)

__all__ = ['AIDecisionProvenance']
