"""Compatibility shim — re-exports `skeleton.shells.ai.orchestrator`.

This shim exists so callers of `skeleton.ai.shell.orchestrator` keep working while `skeleton.shells.ai.orchestrator` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.orchestrator import (
    AIReviewBundle,
    AIExecutionBundle,
    AIShellOrchestrator,
)

__all__ = ['AIReviewBundle', 'AIExecutionBundle', 'AIShellOrchestrator']
