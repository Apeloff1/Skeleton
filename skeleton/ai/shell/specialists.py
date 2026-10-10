"""Compatibility shim — re-exports `skeleton.shells.ai.specialists`.

This shim exists so callers of `skeleton.ai.shell.specialists` keep working while `skeleton.shells.ai.specialists` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.specialists import (
    PlannerSpecialist,
    SpecialistRegistry,
)

__all__ = ['PlannerSpecialist', 'SpecialistRegistry']
