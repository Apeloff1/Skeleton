"""Canonical learning contracts for Skeleton.

Jeeves remains the implementation home during consolidation; consumers should
prefer this package when they need assessment/curriculum behavior without the
rest of the tutor/LLM surface.
"""

from skeleton.jeeves.assessment import (
    AdaptiveTest,
    AssessmentEngine,
    AssessmentError,
    BloomLevel,
    InteractionEvidence,
    SkillModel,
)
from skeleton.jeeves.curriculum import Curriculum, CurriculumError, Lesson

from .service import LearningService, LearningSnapshot

__all__ = [
    "AdaptiveTest",
    "AssessmentEngine",
    "AssessmentError",
    "BloomLevel",
    "Curriculum",
    "CurriculumError",
    "InteractionEvidence",
    "LearningService",
    "LearningSnapshot",
    "Lesson",
    "SkillModel",
]
