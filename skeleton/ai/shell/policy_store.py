"""Compatibility shim — re-exports `skeleton.shells.ai.policy_store`.

This shim exists so callers of `skeleton.ai.shell.policy_store` keep working while `skeleton.shells.ai.policy_store` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.policy_store import (
    AIPolicyRevision,
    AIPolicyConflict,
    AIPolicyStore,
)

__all__ = ['AIPolicyRevision', 'AIPolicyConflict', 'AIPolicyStore']
