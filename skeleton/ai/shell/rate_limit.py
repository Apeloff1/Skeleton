"""Compatibility shim — re-exports `skeleton.shells.ai.rate_limit`.

This shim exists so callers of `skeleton.ai.shell.rate_limit` keep working while `skeleton.shells.ai.rate_limit` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.rate_limit import (
    AIModelRateLimit,
    AIModelRateDecision,
    AIModelRateLimiter,
)

__all__ = ['AIModelRateLimit', 'AIModelRateDecision', 'AIModelRateLimiter']
