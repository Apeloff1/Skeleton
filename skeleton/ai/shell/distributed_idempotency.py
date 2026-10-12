"""Compatibility shim — re-exports `skeleton.shells.ai.distributed_idempotency`.

This shim exists so callers of `skeleton.ai.shell.distributed_idempotency` keep working while `skeleton.shells.ai.distributed_idempotency` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.distributed_idempotency import (
    DistributedIdempotencyConfig,
    DistributedAIIdempotencyRegistry,
)

__all__ = ['DistributedIdempotencyConfig', 'DistributedAIIdempotencyRegistry']
