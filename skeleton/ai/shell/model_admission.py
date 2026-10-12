"""Compatibility shim — re-exports `skeleton.shells.ai.model_admission`.

This shim exists so callers of `skeleton.ai.shell.model_admission` keep working while `skeleton.shells.ai.model_admission` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.model_admission import (
    ModelAdmissionRequirement,
    ModelAdmissionReport,
    AIModelAdmission,
)

__all__ = ['ModelAdmissionRequirement', 'ModelAdmissionReport', 'AIModelAdmission']
