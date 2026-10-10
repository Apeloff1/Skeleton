"""Compatibility shim — re-exports `skeleton.shells.ai.observation_policy`.

This shim exists so callers of `skeleton.ai.shell.observation_policy` keep working while `skeleton.shells.ai.observation_policy` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.observation_policy import (
    ObservationExposure,
    ObservationPolicy,
    ObservationPolicyEngine,
)

__all__ = ['ObservationExposure', 'ObservationPolicy', 'ObservationPolicyEngine']
