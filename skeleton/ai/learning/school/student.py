"""Learner state and durable evidence for the Jeeves school.

Portable extraction from Tutolage's curriculum/progress/analytics model.  This
module deliberately keeps persistence out of the core so adapters can store the
same state in a database, event log, or in-memory session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class SkillState:
    """Evidence-backed state for one skill."""

    skill_id: str
    mastery: float = 0.0
    confidence: float = 0.0
    attempts: int = 0
    successes: int = 0
    last_score: float = 0.0
    last_seen_step: int = 0
    evidence: List[str] = field(default_factory=list)

    def update(self, score: float, *, confidence: float | None = None, step: int = 0, evidence: str | None = None) -> None:
        score = max(0.0, min(1.0, score))
        self.attempts += 1
        self.successes += int(score >= 0.7)
        self.last_score = score
        self.last_seen_step = step
        # Conservative EMA: recent evidence matters, but one lucky answer does
        # not instantly turn a novice into a master.
        alpha = 0.35 if self.attempts > 1 else 0.55
        self.mastery = max(0.0, min(1.0, self.mastery * (1 - alpha) + score * alpha))
        observed_confidence = score if confidence is None else max(0.0, min(1.0, confidence))
        self.confidence = max(0.0, min(1.0, self.confidence * (1 - alpha) + observed_confidence * alpha))
        if evidence and evidence not in self.evidence:
            self.evidence.append(evidence)


@dataclass
class StudentProfile:
    """Minimal learner model Jeeves can safely carry between sessions."""

    student_id: str
    display_name: str = "Learner"
    total_hours: float = 0.0
    energy: float = 1.0
    streak_days: int = 0
    goals: List[str] = field(default_factory=list)
    interests: Set[str] = field(default_factory=set)
    preferences: Dict[str, str] = field(default_factory=dict)
    skills: Dict[str, SkillState] = field(default_factory=dict)
    facts: Dict[str, str] = field(default_factory=dict)

    def skill(self, skill_id: str) -> SkillState:
        if skill_id not in self.skills:
            self.skills[skill_id] = SkillState(skill_id=skill_id)
        return self.skills[skill_id]

    def record_evidence(
        self,
        skill_id: str,
        score: float,
        *,
        confidence: float | None = None,
        minutes: float = 0.0,
        step: int = 0,
        evidence: str | None = None,
    ) -> SkillState:
        self.total_hours = max(0.0, self.total_hours + max(0.0, minutes) / 60.0)
        return self.skill(skill_id).update(
            score,
            confidence=confidence,
            step=step,
            evidence=evidence,
        )

    def readiness(self, skill_id: str, threshold: float = 0.7) -> bool:
        return self.skill(skill_id).mastery >= threshold
