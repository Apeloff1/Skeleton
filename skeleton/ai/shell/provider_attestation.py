"""Compatibility shim — re-exports `skeleton.shells.ai.provider_attestation`.

This shim exists so callers of `skeleton.ai.shell.provider_attestation` keep working while `skeleton.shells.ai.provider_attestation` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.provider_attestation import (
    ProviderAttestation,
    AttestationRequirement,
    AttestationReport,
    ProviderAttestationVerifier,
)

__all__ = ['ProviderAttestation', 'AttestationRequirement', 'AttestationReport', 'ProviderAttestationVerifier']
