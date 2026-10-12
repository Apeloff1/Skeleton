"""Compatibility shim — re-exports `skeleton.shells.ai.distributed_session`.

This shim exists so callers of `skeleton.ai.shell.distributed_session` keep working while `skeleton.shells.ai.distributed_session` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.distributed_session import (
    DistributedSessionConfig,
    DistributedAISessionStore,
)

__all__ = ['DistributedSessionConfig', 'DistributedAISessionStore']
