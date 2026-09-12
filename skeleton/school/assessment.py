"""Assessment and intervention signals for Jeeves.

Tutolage's curriculum layer combines quiz scores, progression and analytics;
its AI debugger/code-intelligence layers add edge-case, bug, security and
performance feedback.  This module turns those ideas into a deterministic
evidence model that a model-backed Jeeves can consume or enrich.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class AssessmentKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    FORMATIVE = "formative"
    SUMMATIVE = "summative"
    PRACTICE = "practice"
    PROJECT = "project"


@dataclass(frozen=True)
class AssessmentEvidence:
    skill_id: str
    kind: AssessmentKind
    score: float
    confidence: float | None = None
    hints_used: int = 0
    attempts: int = 1
    time_minutes: float = 0.0
    misconception: str | None = None
    tags: tuple[str, ...] = ()

    def normalized_score(self) -> float:
        return max(0.0, min(1.0, self.score))

    def adjusted_mastery_signal(self) -> float:
        """Discount heavily scaffolded success without punishing normal help."""
        score = self.normalized_score()
        hint_penalty = min(0.2, max(0, self.hints_used) * 0.04)
        retry_penalty = min(0.1, max(0, self.attempts - 1) * 0.02)
        return max(0.0, score - hint_penalty - retry_penalty)


@dataclass(frozen=True)
class Intervention:
    kind: str
    reason: str
    intensity: int
    skill_id: str


@dataclass
class AssessmentEngine:
    history: List[AssessmentEvidence] = field(default_factory=list)

    def record(self, evidence: AssessmentEvidence) -> None:
        if not 0.0 <= evidence.score <= 1.0:
            raise ValueError("assessment score must be between 0 and 1")
        if evidence.hints_used < 0 or evidence.attempts < 1:
            raise ValueError("hints_used must be non-negative and attempts >= 1")
        self.history.append(evidence)

    def recent(self, skill_id: str, limit: int = 5) -> List[AssessmentEvidence]:
        return [item for item in reversed(self.history) if item.skill_id == skill_id][:limit]

    def intervention_for(self, skill_id: str) -> Intervention | None:
        recent = self.recent(skill_id)
        if not recent:
            return Intervention("diagnose", "No evidence yet; establish a baseline.", 2, skill_id)
        average = sum(item.normalized_score() for item in recent) / len(recent)
        latest = recent[0]
        if latest.misconception:
            return Intervention("targeted_remediation", f"Address misconception: {latest.misconception}", 3, skill_id)
        if average < 0.5:
            return Intervention("scaffold", "Mastery signal is low; increase worked examples and hints.", 3, skill_id)
        if average < 0.7:
            return Intervention("practice", "Build fluency with short retrieval and interleaving.", 2, skill_id)
        if average > 0.9 and latest.hints_used == 0:
            return Intervention("challenge", "Strong independent performance; raise transfer difficulty.", 2, skill_id)
        return Intervention("review", "Maintain retrieval and check for transfer.", 1, skill_id)

    def score_summary(self, skill_id: str) -> dict[str, float | int]:
        recent = self.recent(skill_id, limit=20)
        if not recent:
            return {"attempts": 0, "average": 0.0, "independent_average": 0.0}
        independent = [item.normalized_score() for item in recent if item.hints_used == 0]
        return {
            "attempts": len(recent),
            "average": sum(item.normalized_score() for item in recent) / len(recent),
            "independent_average": sum(independent) / len(independent) if independent else 0.0,
        }
