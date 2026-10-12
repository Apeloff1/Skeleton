"""Compatibility shim — re-exports `skeleton.shells.ai.review_queue`.

This shim exists so callers of `skeleton.ai.shell.review_queue` keep working while `skeleton.shells.ai.review_queue` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.review_queue import (
    ReviewState,
    ReviewQueueItem,
    ReviewQueueConflict,
    AIReviewQueue,
)

__all__ = ['ReviewState', 'ReviewQueueItem', 'ReviewQueueConflict', 'AIReviewQueue']
