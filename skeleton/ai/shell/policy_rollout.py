"""Compatibility shim — re-exports `skeleton.shells.ai.policy_rollout`.

This shim exists so callers of `skeleton.ai.shell.policy_rollout` keep working while `skeleton.shells.ai.policy_rollout` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.policy_rollout import (
    AIPolicyRolloutPhase,
    AIPolicyRollout,
    AIPolicyRolloutManager,
)

__all__ = ['AIPolicyRolloutPhase', 'AIPolicyRollout', 'AIPolicyRolloutManager']
