"""Compatibility shim — re-exports `skeleton.shells.ai.sandbox_lifecycle`.

This shim exists so callers of `skeleton.ai.shell.sandbox_lifecycle` keep working while `skeleton.shells.ai.sandbox_lifecycle` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.sandbox_lifecycle import (
    ArtifactScanEvidence,
    SandboxLifecycleError,
    SandboxLifecycleEvidence,
    SandboxLifecycleReport,
    SecretProjectionEvidence,
    verify_sandbox_lifecycle,
)

__all__ = ['ArtifactScanEvidence', 'SandboxLifecycleError', 'SandboxLifecycleEvidence', 'SandboxLifecycleReport', 'SecretProjectionEvidence', 'verify_sandbox_lifecycle']
