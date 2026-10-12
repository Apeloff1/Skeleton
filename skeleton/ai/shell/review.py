"""Compatibility shim — re-exports `skeleton.shells.ai.review`.

This shim exists so callers of `skeleton.ai.shell.review` keep working while `skeleton.shells.ai.review` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.review import (
    ReviewAction,
    AIReviewView,
    AIReviewBuilder,
)

__all__ = ['ReviewAction', 'AIReviewView', 'AIReviewBuilder']
