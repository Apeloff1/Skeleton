"""Compatibility shim — re-exports `skeleton.shells.ai.sandbox_attestation`.

This shim exists so callers of `skeleton.ai.shell.sandbox_attestation` keep working while `skeleton.shells.ai.sandbox_attestation` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.sandbox_attestation import (
    SandboxCapabilities,
    SandboxAttestationReport,
    SandboxAttestationVerifier,
)

__all__ = ['SandboxCapabilities', 'SandboxAttestationReport', 'SandboxAttestationVerifier']
