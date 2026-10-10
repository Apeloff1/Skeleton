"""Compatibility shim — re-exports `skeleton.shells.ai.regression`.

This shim exists so callers of `skeleton.ai.shell.regression` keep working while `skeleton.shells.ai.regression` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.regression import (
    RegressionRecord,
    RegressionComparison,
    AIRegressionHistory,
)

__all__ = ['RegressionRecord', 'RegressionComparison', 'AIRegressionHistory']
