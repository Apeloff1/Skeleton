"""Jeeves package — AI tutor brain with session tracking surface."""

from .core import Jeeves, JeevesCore, Session, SessionMode, SYSTEM_LAWS, Turn
from .matrices import ClomMatrix, KremMatrix, SamMatrix
from .rag import RagMemory
from .tactical import Advice, TacticalBrain, WorldModel
from .builder import BuildPlan, BuilderBrain
from .assessment import (
    AdaptiveTest,
    AssessmentEngine,
    AssessmentError,
    BloomLevel,
    InteractionEvidence,
    SkillModel,
)
from .cocoding import CoCodingOrchestrator, CoCodingSession, SkillLevel, Stage
from .curriculum import Curriculum, CurriculumError, Lesson
from .feedback import (
    FeedbackCollector,
    FeedbackError,
    FeedbackKind,
    FeedbackRecord,
)
from .pedagogy import Hint, HintLevel, PedagogyEngine, PedagogyError, Scaffold
from .reflection import ReflectionBuilder, ReflectionPoint, ReflectionReport
from .review import (
    CodeReviewer,
    Finding,
    FindingSeverity,
    ReviewError,
    ReviewRule,
    default_reviewer,
)
from .safety import SafetyError, SafetyFlag, SafetyGuard, SafetyLevel
from .templates import PromptRegistry, PromptTemplate, TemplateError
from .tracking import SessionTracker, SessionTracking
from .troubleshooting import Troubleshooter, TroubleshootingStep

__all__ = [
    "Jeeves",
    "JeevesCore",
    "Session",
    "SessionMode",
    "SYSTEM_LAWS",
    "Turn",
    "ClomMatrix",
    "KremMatrix",
    "SamMatrix",
    "RagMemory",
    "Advice",
    "TacticalBrain",
    "WorldModel",
    "BuildPlan",
    "BuilderBrain",
    "AdaptiveTest",
    "AssessmentEngine",
    "AssessmentError",
    "BloomLevel",
    "InteractionEvidence",
    "SkillModel",
    "CoCodingOrchestrator",
    "CoCodingSession",
    "SkillLevel",
    "Stage",
    "Curriculum",
    "CurriculumError",
    "Lesson",
    "FeedbackCollector",
    "FeedbackError",
    "FeedbackKind",
    "FeedbackRecord",
    "Hint",
    "HintLevel",
    "PedagogyEngine",
    "PedagogyError",
    "Scaffold",
    "ReflectionBuilder",
    "ReflectionPoint",
    "ReflectionReport",
    "CodeReviewer",
    "Finding",
    "FindingSeverity",
    "ReviewError",
    "ReviewRule",
    "default_reviewer",
    "SafetyError",
    "SafetyFlag",
    "SafetyGuard",
    "SafetyLevel",
    "PromptRegistry",
    "PromptTemplate",
    "TemplateError",
    "SessionTracker",
    "SessionTracking",
    "Troubleshooter",
    "TroubleshootingStep",
]
