"""Jeeves package — GameForge tutor brain + LLM orchestration surface."""

from .core import Jeeves, Session, SessionMode, SYSTEM_LAWS, Turn
from .llm_core import JeevesCore, MemoryManager
from .matrices import ClomMatrix, KremMatrix, SamMatrix
from .matrices_llm import (
    CompressedLearnedOutcomeModel,
    KnowledgeRetentionMatrix,
    SemanticAssociationMap,
)
from .rag import RagMemory
from .tactical import Advice, TacticalBrain, WorldModel
from .builder import BuildPlan, BuilderBrain
from .providers import (
    AnthropicProvider,
    LLMProvider,
    LocalEchoProvider,
    OpenAIProvider,
    get_provider,
)
from .citations import Citation, CitationEngine
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

# Keep CORTEX mode lazy without falling back merely because _cortex has not
# been materialised yet. The core object intentionally lazy-loads the real
# neocortex, so a first CORTEX request must use that same lifecycle-bound model.
_core_think = Jeeves.think

def _jeeves_think_lazy_cortex(self, stimulus: str, *, context=None):
    cortex = self.cortex
    if callable(getattr(cortex, "think", None)):
        trace = cortex.think(stimulus, context)
        self._bus.emit("jeeves.cortex.thought", {
            "fp": trace.fingerprint,
            "used_own": trace.used_own,
            "hive": trace.hive_value,
        })
        return trace
    return _core_think(self, stimulus, context=context)

Jeeves.think = _jeeves_think_lazy_cortex

__all__ = [
    "Jeeves",
    "JeevesCore",
    "Session",
    "SessionMode",
    "SYSTEM_LAWS",
    "Turn",
    "MemoryManager",
    "ClomMatrix",
    "KremMatrix",
    "SamMatrix",
    "SemanticAssociationMap",
    "CompressedLearnedOutcomeModel",
    "KnowledgeRetentionMatrix",
    "RagMemory",
    "Advice",
    "TacticalBrain",
    "WorldModel",
    "BuildPlan",
    "BuilderBrain",
    "LLMProvider",
    "LocalEchoProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "Citation",
    "CitationEngine",
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
