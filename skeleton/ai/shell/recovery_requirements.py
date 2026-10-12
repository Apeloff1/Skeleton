"""Compatibility shim — re-exports `skeleton.shells.ai.recovery_requirements`.

This shim exists so callers of `skeleton.ai.shell.recovery_requirements` keep working while `skeleton.shells.ai.recovery_requirements` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.recovery_requirements import (
    DurableRecoveryRequirementManifest,
    SignedDurableRecoveryRequirementManifest,
    DurableRecoveryRequirementVerification,
    DurableRecoveryRequirementConflict,
    DurableRecoveryRequirementStore,
)

__all__ = ['DurableRecoveryRequirementManifest', 'SignedDurableRecoveryRequirementManifest', 'DurableRecoveryRequirementVerification', 'DurableRecoveryRequirementConflict', 'DurableRecoveryRequirementStore']
