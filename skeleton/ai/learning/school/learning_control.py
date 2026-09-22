"""Jeeves learning-control matrices mined from Interesting-22.

Interesting-22's Jeeves core describes SAM (skill acquisition), CLOM
(cognitive load) and KREM (knowledge retention/evolution), with rules for
adjusting difficulty, varying contexts, spacing review and simplifying
presentation.  This module ports those decision semantics as typed, testable
policy instead of copying the original API/RAG implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LearningState:
    mastery: float = 0.5
    acquisition_rate: float = 0.5
    retention_rate: float = 1.0
    transfer_rate: float = 1.0
    depth_score: float = 1.0
    cognitive_load: float = 0.5
    time_since_review_hours: float = 0.0
    response_time_ratio: float = 1.0

    def validate(self) -> None:
        for name in (
            "mastery",
            "acquisition_rate",
            "retention_rate",
            "transfer_rate",
            "depth_score",
            "cognitive_load",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.time_since_review_hours < 0 or self.response_time_ratio < 0:
            raise ValueError("time_since_review_hours and response_time_ratio must be non-negative")


@dataclass(frozen=True)
class LearningControlDecision:
    difficulty_adjustment: str
    content_strategy: str
    practice_schedule: str
    retention_strategy: str
    rationale: tuple[str, ...]


class LearningControl:
    """Apply SAM/CLOM/KREM-style rules to a learner snapshot."""

    def decide(self, state: LearningState) -> LearningControlDecision:
        state.validate()
        rationale: list[str] = []

        # SAM: acquisition, retention, transfer and depth determine the
        # direction of practice rather than raw quiz score alone.
        if state.acquisition_rate < 0.4:
            difficulty = "reduce_difficulty"
            rationale.append("acquisition is declining")
        elif state.depth_score < 0.3:
            difficulty = "stabilize_fundamentals"
            rationale.append("depth is low; strengthen fundamentals")
        elif state.cognitive_load > 0.8:
            difficulty = "reduce_complexity"
            rationale.append("cognitive load is high")
        elif state.cognitive_load < 0.3 and state.mastery >= 0.7:
            difficulty = "increase_challenge"
            rationale.append("low load plus solid mastery permits a challenge")
        else:
            difficulty = "hold"

        if state.transfer_rate < 0.5:
            content = "varied_contexts"
            rationale.append("transfer is weak; vary application contexts")
        elif state.retention_rate < 0.7:
            content = "retrieval_plus_examples"
            rationale.append("retention is weak; combine retrieval with examples")
        else:
            content = "productive_application"

        practice = "increase_spaced_repetition" if state.retention_rate < 0.7 else "maintain_spacing"
        retention = "scheduled_review_needed" if state.time_since_review_hours > 24 else "continue_schedule"
        if state.response_time_ratio > 2.0:
            content = "simplify_presentation"
            rationale.append("response time exceeds twice baseline; simplify presentation")

        return LearningControlDecision(difficulty, content, practice, retention, tuple(rationale))
