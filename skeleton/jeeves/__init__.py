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
from .review import (
    CodeReviewer,
    Finding,
    FindingSeverity,
    ReviewError,
    ReviewRule,
    default_reviewer,
)
from .templates import PromptRegistry, PromptTemplate, TemplateError

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
    "CodeReviewer",
    "Finding",
    "FindingSeverity",
    "ReviewError",
    "ReviewRule",
    "default_reviewer",
    "PromptRegistry",
    "PromptTemplate",
    "TemplateError",
]
