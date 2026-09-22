"""AI policy distilled from the Tutolage/Jeeves learning systems.

This is framework policy, not the original web/API implementation. It gives
Skeleton agents a deterministic way to choose learning stage, difficulty,
scaffolding and interaction mode while preserving learner agency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class LearningStage(str, Enum):
    ONBOARDING = "onboarding"
    FOUNDATION = "foundation"
    GROWTH = "growth"
    MASTERY = "mastery"


class InteractionMode(str, Enum):
    TEACH = "teach"
    PRACTICE = "practice"
    CHALLENGE = "challenge"
    REVIEW = "review"
    EXPLORE = "explore"
    REFLECT = "reflect"


@dataclass(frozen=True)
class LearningPolicy:
    stage: LearningStage
    difficulty_cap: float
    scaffolding: str
    style: str
    focus: str
    xp_multiplier: float


POLICIES = {
    LearningStage.ONBOARDING: LearningPolicy(LearningStage.ONBOARDING, 0.30, "heavy", "nurturing", "confidence_building", 1.5),
    LearningStage.FOUNDATION: LearningPolicy(LearningStage.FOUNDATION, 0.50, "moderate", "instructive", "core_concepts", 1.2),
    LearningStage.GROWTH: LearningPolicy(LearningStage.GROWTH, 0.80, "light", "mentoring", "advanced_application", 1.0),
    LearningStage.MASTERY: LearningPolicy(LearningStage.MASTERY, 1.00, "minimal", "collaborative", "expertise", 0.8),
}


def stage_for_hours(total_hours: float) -> LearningStage:
    """Map accumulated learning time to a managed learning stage."""
    if total_hours < 0:
        raise ValueError("total_hours must be non-negative")
    if total_hours < 5:
        return LearningStage.ONBOARDING
    if total_hours < 50:
        return LearningStage.FOUNDATION
    if total_hours < 200:
        return LearningStage.GROWTH
    return LearningStage.MASTERY


def choose_difficulty(
    stage: LearningStage,
    recent_performance: Sequence[float] = (),
    emotional_state: str = "neutral",
) -> float:
    """Choose a bounded challenge level using a ZPD-style heuristic."""
    policy = POLICIES[stage]
    scores = tuple(float(x) for x in recent_performance[-10:])
    if any(x < 0 or x > 1 for x in scores):
        raise ValueError("performance scores must be in [0, 1]")
    base = (sum(scores) / len(scores)) if scores else policy.difficulty_cap * 0.3
    if scores and base > 0.85:
        base += 0.10
    elif scores and base < 0.70:
        base -= 0.10
    adjustment = {
        "frustrated": -0.15, "confused": -0.10, "tired": -0.15,
        "overwhelmed": -0.20, "anxious": -0.10,
        "confident": 0.05, "excited": 0.10, "focused": 0.05,
    }.get(emotional_state, 0.0)
    return round(max(0.10, min(policy.difficulty_cap, base + adjustment)), 2)


def interaction_mode(*, performance: float | None, emotional_state: str, learner_requested: str | None = None) -> InteractionMode:
    """Select an interaction mode without overriding an explicit learner choice."""
    if learner_requested:
        return InteractionMode(learner_requested)
    if emotional_state in {"frustrated", "confused", "overwhelmed"}:
        return InteractionMode.REVIEW
    if performance is not None and performance >= 0.85:
        return InteractionMode.CHALLENGE
    if performance is not None and performance < 0.60:
        return InteractionMode.TEACH
    return InteractionMode.PRACTICE
