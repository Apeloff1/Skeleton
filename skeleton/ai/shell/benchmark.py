"""Compatibility shim — re-exports `skeleton.shells.ai.benchmark`.

This shim exists so callers of `skeleton.ai.shell.benchmark` keep working while `skeleton.shells.ai.benchmark` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.benchmark import (
    AIBenchmarkCase,
    default_benchmark_cases,
)

__all__ = ['AIBenchmarkCase', 'default_benchmark_cases']
