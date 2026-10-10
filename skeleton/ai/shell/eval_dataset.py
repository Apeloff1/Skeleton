"""Compatibility shim — re-exports `skeleton.shells.ai.eval_dataset`.

This shim exists so callers of `skeleton.ai.shell.eval_dataset` keep working while `skeleton.shells.ai.eval_dataset` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.eval_dataset import (
    AIEvalCase,
    AIEvalDataset,
)

__all__ = ['AIEvalCase', 'AIEvalDataset']
