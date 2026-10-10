"""Compatibility shim — re-exports `skeleton.shells.ai.plan_cache`.

This shim exists so callers of `skeleton.ai.shell.plan_cache` keep working while `skeleton.shells.ai.plan_cache` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.plan_cache import (
    CachedAIPlan,
    AIPlanCache,
)

__all__ = ['CachedAIPlan', 'AIPlanCache']
