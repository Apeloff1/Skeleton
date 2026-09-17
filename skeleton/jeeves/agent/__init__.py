"""Jeeves evidence-first agent runtime.

Public imports are kept explicit so application code can build a runtime
without reaching into implementation modules.
"""

from .cognition import (
    CognitionError,
    ContextBudget,
    ContextCompiler,
    ContextPacket,
    ContextSection,
    EvidenceContextPolicy,
    FINAL_RESPONSE_SCHEMA,
    FinalDraft,
    FinalDraftDecoder,
    MemoryContextPolicy,
    PromptCompiler,
    RunScratchpad,
    ScratchEntry,
    approximate_tokens,
)
from .evidence import (
    Contradiction,
    EvidenceArtifact,
    EvidenceLedger,
    GroundingGate,
    GroundingPolicy,
    GroundingReport,
    LearningEvidenceBridge,
    evidence_from_payload,
)
from .evaluation import (
    AgentInvariantChecker,
    CalibrationEvaluator,
    CalibrationReport,
    CalibrationSample,
    EvalCase,
    EvalExpectation,
    EvalResult,
    EvaluationSuite,
    RunEvaluator,
)
from .memory import (
    ConsolidationCandidate,
    InMemoryStore,
    MemoryConsolidator,
    MemoryHit,
    MemoryManager,
    MemoryNamespace,
    MemoryPromotionPolicy,
    MemoryRecord,
    MemoryRetriever,
    RetrievalWeights,
)
from .planning import (
    ModelPlanParser,
    PlanScheduler,
    PlanValidationReport,
    PlanValidator,
    ReplanDecision,
    ReplanPolicy,
)
from .policy import (
    CompositePolicy,
    ConfidencePolicy,
    ExecutionPolicy,
    PolicyContext,
    PolicyDecision,
)
from .provider import (
    CircuitBreaker,
    CircuitState,
    DeterministicProvider,
    LegacyProviderAdapter,
    ModelCapabilities,
    ProviderRouter,
    RecordingProvider,
    RetryPolicy,
)
from .runtime import (
    AgentConfig,
    InMemoryCheckpointer,
    JeevesAgentRuntime,
    RunCheckpoint,
    RunInputs,
)
from .telemetry import MetricsRegistry, SpanRecord, TraceEvent, TraceLedger, Tracer
from .tools import (
    ArgumentRule,
    ToolExecutionContext,
    ToolExecutor,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
    function_tool,
)
from .types import (
    AgentContractError,
    AgentPhase,
    AgentResult,
    Budget,
    Claim,
    Decision,
    EvidenceKind,
    EvidenceRef,
    Goal,
    MemoryKind,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    TerminationReason,
    ToolCall,
    ToolObservation,
    Usage,
    canonical_json,
    stable_fingerprint,
    stable_id,
)
from .verification import (
    CheckSeverity,
    PredicateRegistry,
    PredicateRequest,
    PredicateSpec,
    StepVerifier,
    VerificationCheck,
    VerificationDirectiveParser,
    VerificationError,
    VerificationPolicy,
    VerificationReport,
    parse_advisory_json,
)

__all__ = [name for name in globals() if not name.startswith("_")]
