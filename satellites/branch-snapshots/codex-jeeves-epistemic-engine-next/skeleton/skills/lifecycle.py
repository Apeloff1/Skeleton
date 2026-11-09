"""Promotion and rollback gates for filesystem-backed skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .manifest import SkillManifest, SkillState
from .store import SkillStore


@dataclass(frozen=True)
class PromotionPolicy:
    minimum_success_rate: float = 0.8
    minimum_attempts: int = 5
    maximum_regressions: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_success_rate <= 1.0:
            raise ValueError("minimum_success_rate must be between 0 and 1")
        if self.minimum_attempts < 1 or self.maximum_regressions < 0:
            raise ValueError("promotion thresholds must be non-negative")


class SkillLifecycle:
    """Own skill state transitions without coupling to an execution engine."""

    def __init__(self, store: SkillStore, policy: PromotionPolicy | None = None) -> None:
        self.store = store
        self.policy = policy or PromotionPolicy()

    def evaluate(self, state: SkillState) -> dict[str, Any]:
        reasons: list[str] = []
        if state.attempts < self.policy.minimum_attempts:
            reasons.append("insufficient_attempts")
        if state.success_rate < self.policy.minimum_success_rate:
            reasons.append("success_rate_below_threshold")
        if state.regressions > self.policy.maximum_regressions:
            reasons.append("regressions_exceeded")
        return {"eligible": not reasons, "reasons": reasons, "success_rate": state.success_rate, "attempts": state.attempts, "regressions": state.regressions}

    def promote(self, manifest: SkillManifest, state: SkillState) -> SkillState:
        result = self.evaluate(state)
        if not result["eligible"]:
            raise ValueError(f"skill is not promotable: {', '.join(result['reasons'])}")
        state.status = "promoted"
        state.metadata = {**state.metadata, "promotion": result}
        self.store.save(manifest, state)
        return state

    def quarantine(self, manifest: SkillManifest, state: SkillState, reason: str) -> SkillState:
        if not reason.strip():
            raise ValueError("quarantine reason is required")
        state.status = "quarantined"
        state.metadata = {**state.metadata, "quarantine_reason": reason}
        self.store.save(manifest, state)
        return state
