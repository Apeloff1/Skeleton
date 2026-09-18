"""AI-facing shell control primitives."""

from skeleton.shells.ai.catalog import AIToolCard, AIToolCatalog
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.guardrails import GuardrailFinding, GuardrailReport, ModelOutputGuard
from skeleton.shells.ai.model_port import AIModelPort, CallableAIModelPort, ModelCapabilities
from skeleton.shells.ai.policy import AIPolicyDecision, AIShellPolicy, AutonomyMode
from skeleton.shells.ai.protocol import (
    AI_MODEL_PROTOCOL_VERSION,
    AIModelRequest,
    AIModelResponse,
    ModelProtocolError,
    parse_model_response,
)
from skeleton.shells.ai.risk import AIRiskAssessor, RiskAssessment, RiskBand, RiskDimension
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
    IntentConstraint,
    IntentKind,
    VerificationCriterion,
)

__all__ = [
    "AIAction",
    "AIIntent",
    "AIModelPort",
    "AIModelRequest",
    "AIModelResponse",
    "AIPlanProposal",
    "AIPolicyDecision",
    "AIRiskAssessor",
    "AIShellPolicy",
    "AIToolCard",
    "AIToolCatalog",
    "AI_MODEL_PROTOCOL_VERSION",
    "AutonomyMode",
    "CallableAIModelPort",
    "EffectContract",
    "EffectKind",
    "EffectRegistry",
    "GuardrailFinding",
    "GuardrailReport",
    "IntentConstraint",
    "IntentKind",
    "ModelCapabilities",
    "ModelOutputGuard",
    "ModelProtocolError",
    "RiskAssessment",
    "RiskBand",
    "RiskDimension",
    "VerificationCriterion",
    "parse_model_response",
]
