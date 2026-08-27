"""Jeeves package — the AI tutor brain."""

from .cocoding import CoCodingOrchestrator, CoCodingSession, SkillLevel, Stage
from .assessment import (
    AdaptiveTest,
    AssessmentEngine,
    AssessmentError,
    BloomLevel,
    InteractionEvidence,
    SkillModel,
)
from .curriculum import Curriculum, CurriculumError, Lesson
from .pedagogy import Hint, HintLevel, PedagogyEngine, PedagogyError, Scaffold

__all__ = [
    "CoCodingOrchestrator",
    "CoCodingSession",
    "SkillLevel",
    "Stage",
    "AdaptiveTest",
    "AssessmentEngine",
    "AssessmentError",
    "BloomLevel",
    "InteractionEvidence",
    "SkillModel",
    "Curriculum",
    "CurriculumError",
    "Lesson",
    "Hint",
    "HintLevel",
    "PedagogyEngine",
    "PedagogyError",
    "Scaffold",
]
