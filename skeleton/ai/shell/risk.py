"""Compatibility shim — re-exports `skeleton.shells.ai.risk`.

This shim exists so callers of `skeleton.ai.shell.risk` keep working while `skeleton.shells.ai.risk` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.risk import (
    RiskBand,
    RiskDimension,
    RiskAssessment,
    AIRiskAssessor,
)

__all__ = ['RiskBand', 'RiskDimension', 'RiskAssessment', 'AIRiskAssessor']
