"""Compatibility shim — re-exports `skeleton.shells.ai.distributed_review`.

This shim exists so callers of `skeleton.ai.shell.distributed_review` keep working while `skeleton.shells.ai.distributed_review` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.distributed_review import (
    DistributedReviewRecord,
    DistributedReviewClaim,
    DistributedAIReviewQueue,
)

__all__ = ['DistributedReviewRecord', 'DistributedReviewClaim', 'DistributedAIReviewQueue']
