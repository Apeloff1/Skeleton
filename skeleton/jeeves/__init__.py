"""Jeeves package — GameForge tutor brain + LLM orchestration surface."""

from skeleton.kernel.errors import SessionError

from .core import Jeeves, Session, SessionMode, SYSTEM_LAWS, Turn
from .llm_core import JeevesCore, MemoryManager
from .evidence_core import EvidenceJeevesCore, EvidenceResult
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

# Harden public session mutation at the package boundary while preserving the
# canonical core implementation. Importing skeleton.jeeves.core still executes
# this package initializer first, so callers observe the same hardened class.
_core_open_session = Jeeves.open_session


def _require_session_mode(mode: SessionMode) -> SessionMode:
    if not isinstance(mode, SessionMode):
        raise SessionError("invalid session mode", context={"mode": str(mode)[:64]})
    return mode


def _jeeves_open_session_resilient(self, user_id, *, mode=SessionMode.TUTORING):
    mode = _require_session_mode(mode)
    return _core_open_session(self, user_id, mode=mode)


def _jeeves_set_mode_resilient(self, session_id: str, mode: SessionMode):
    session = self._get(session_id)
    mode = _require_session_mode(mode)
    if not session.is_open:
        raise SessionError("session is closed", context={"session_id": session_id})
    session.mode = mode
    self._bus.emit("jeeves.session.mode_changed", {
        "session_id": session_id,
        "mode": mode.value,
    })
    return session


def _jeeves_ask_resilient(self, session_id: str, message: str, *, context=None) -> str:
    """Commit a learner exchange only after a valid reply is produced."""
    if not isinstance(message, str) or not message.strip():
        raise SessionError("message must be a non-empty string")
    if len(message) > self._max_message_chars:
        raise SessionError(
            "message exceeds size limit",
            context={"max_message_chars": self._max_message_chars},
        )
    if context is not None and not isinstance(context, dict):
        raise SessionError("context must be an object")

    session = self._get(session_id)
    self._ensure_turn_capacity(session, 2)
    prior_history = [Turn(role=t.role, content=t.content, at=t.at) for t in session.turns]
    start_turns = len(session.turns)
    session.add_turn("learner", message)
    ctx = dict(context or {})
    ctx["mode"] = session.mode.value

    try:
        if session.mode in (SessionMode.TACTICAL, SessionMode.BUILDER):
            telemetry = ctx.get("telemetry") or {}
            reply = self._brain_get().recommend_next(telemetry).text
        elif session.mode is SessionMode.CORTEX:
            reply = self.think(message, context=ctx).amalgam.text
        else:
            reply = self._responder(message, prior_history, ctx)
        if not isinstance(reply, str) or not reply.strip():
            raise SessionError(
                "responder returned an invalid reply",
                context={"session_id": session_id},
            )
        session.add_turn("jeeves", reply)
    except BaseException:
        del session.turns[start_turns:]
        self._bus.emit("jeeves.turn.failed", {"session_id": session_id})
        raise

    self._bus.emit("jeeves.turn.completed", {
        "session_id": session_id,
        "turns": len(session.turns),
    })
    return reply


Jeeves.open_session = _jeeves_open_session_resilient
Jeeves.set_mode = _jeeves_set_mode_resilient
Jeeves.ask = _jeeves_ask_resilient

__all__ = [
    "Jeeves",
    "JeevesCore",
    "EvidenceJeevesCore",
    "EvidenceResult",
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
