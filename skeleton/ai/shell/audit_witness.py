"""Compatibility shim — re-exports `skeleton.shells.ai.audit_witness`.

This shim exists so callers of `skeleton.ai.shell.audit_witness` keep working while `skeleton.shells.ai.audit_witness` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.audit_witness import (
    AIAuditWitness,
    SignedAIAuditWitness,
    AuditWitnessHead,
    AuditWitnessVerification,
    AIAuditWitnessStore,
)

__all__ = ['AIAuditWitness', 'SignedAIAuditWitness', 'AuditWitnessHead', 'AuditWitnessVerification', 'AIAuditWitnessStore']
