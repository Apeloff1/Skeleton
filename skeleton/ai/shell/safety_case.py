"""Compatibility shim — re-exports `skeleton.shells.ai.safety_case`.

This shim exists so callers of `skeleton.ai.shell.safety_case` keep working while `skeleton.shells.ai.safety_case` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.safety_case import (
    SafetyCaseState,
    SafetyCasePolicy,
    SafetyCase,
    AISafetyCaseBuilder,
)

__all__ = ['SafetyCaseState', 'SafetyCasePolicy', 'SafetyCase', 'AISafetyCaseBuilder']
