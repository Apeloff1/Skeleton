"""Compatibility shim — re-exports `skeleton.shells.ai.distributed_policy`.

This shim exists so callers of `skeleton.ai.shell.distributed_policy` keep working while `skeleton.shells.ai.distributed_policy` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.distributed_policy import (
    DistributedPolicyConfig,
    DistributedAIPolicyStore,
)

__all__ = ['DistributedPolicyConfig', 'DistributedAIPolicyStore']
