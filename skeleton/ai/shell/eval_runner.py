"""Compatibility shim — re-exports `skeleton.shells.ai.eval_runner`.

This shim exists so callers of `skeleton.ai.shell.eval_runner` keep working while `skeleton.shells.ai.eval_runner` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.eval_runner import (
    AIEvalCaseResult,
    AIEvalRun,
    AIEvalRunner,
)

__all__ = ['AIEvalCaseResult', 'AIEvalRun', 'AIEvalRunner']
