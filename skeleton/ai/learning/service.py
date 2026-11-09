"""Canonical learning facade over Jeeves assessment and curriculum primitives.

The consolidation architecture treats learning as a first-class layer.  This
module provides that stable import surface without copying the mature Jeeves
implementations or coupling the layer to any LLM/provider integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from skeleton.jeeves.assessment import (
    AssessmentEngine,
    BloomLevel,
    InteractionEvidence,
    SkillModel,
)
from skeleton.jeeves.curriculum import Curriculum, Lesson


@dataclass(frozen=True)
class LearningSnapshot:
    """Small immutable view of the current learning state."""

    ready_lesson_ids: Tuple[str, ...]
    weakest_skill_ids: Tuple[str, ...]


class LearningService:
    """Provider-neutral entry point for assessment and curriculum sequencing.

    Existing Jeeves primitives remain the source of truth.  The facade gives
    callers a canonical ``skeleton.learning`` boundary while consolidation can
    continue behind it without forcing application code to depend on Jeeves'
    internal module layout.
    """

    def __init__(
        self,
        *,
        assessment: Optional[AssessmentEngine] = None,
        curriculum: Optional[Curriculum] = None,
    ) -> None:
        self.assessment = assessment or AssessmentEngine()
        self.curriculum = curriculum or Curriculum()

    def add_lesson(self, lesson: Lesson) -> None:
        self.curriculum.add(lesson)

    def observe(self, evidence: InteractionEvidence) -> SkillModel:
        return self.assessment.observe(evidence)

    def record(
        self,
        skill_id: str,
        *,
        correct: bool,
        bloom_level: BloomLevel = BloomLevel.UNDERSTAND,
        latency_s: float = 0.0,
        hints_used: int = 0,
    ) -> SkillModel:
        """Record one validated learning interaction."""
        return self.observe(
            InteractionEvidence(
                skill_id=skill_id,
                correct=correct,
                bloom_level=bloom_level,
                latency_s=latency_s,
                hints_used=hints_used,
            )
        )

    def mastery(self, skill_id: str) -> Optional[float]:
        return self.assessment.mastery(skill_id)

    def ready_lessons(self) -> Tuple[Lesson, ...]:
        return self.curriculum.ready(self.assessment)

    def next_lesson(self) -> Optional[Lesson]:
        return self.curriculum.next_for(self.assessment)

    def snapshot(self, *, weakest: int = 3) -> LearningSnapshot:
        ready_ids = tuple(lesson.lesson_id for lesson in self.ready_lessons())
        weakest_ids = tuple(
            skill.skill_id for skill in self.assessment.weakest(weakest)
        )
        return LearningSnapshot(
            ready_lesson_ids=ready_ids,
            weakest_skill_ids=weakest_ids,
        )
