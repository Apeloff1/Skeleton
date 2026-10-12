"""Compatibility shim — re-exports `skeleton.shells.ai.sandbox_backend`.

This shim exists so callers of `skeleton.ai.shell.sandbox_backend` keep working while `skeleton.shells.ai.sandbox_backend` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.sandbox_backend import (
    SandboxPlanExecutor,
    SandboxBinding,
    VerifiedSandboxExecutionBackend,
)

__all__ = ['SandboxPlanExecutor', 'SandboxBinding', 'VerifiedSandboxExecutionBackend']
