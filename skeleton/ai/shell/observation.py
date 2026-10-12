"""Compatibility shim — re-exports `skeleton.shells.ai.observation`.

This shim exists so callers of `skeleton.ai.shell.observation` keep working while `skeleton.shells.ai.observation` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.observation import (
    AIObservation,
    ObservationBuilder,
)

__all__ = ['AIObservation', 'ObservationBuilder']
