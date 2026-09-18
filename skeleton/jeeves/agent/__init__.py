"""Jeeves evidence-first cognitive agent runtime.

Public imports are explicit enough for application code to assemble the runtime
without reaching through implementation paths. The package surface exposes the
bounded runtime plus scientific layers for cue-first associative context, typed
probability and uncertainty, semantic nuance with empirical validation,
perpendicular tangent continuity, factorized causal control, and guarded
execution with tamper-evident replay.
"""

from .action_model import (
    ActionEpisode,
    ActionModelError,
    BetaPosterior,
    CompositeSkillPlan,
    CompositeStep,
    ContextPerformance,
    ContextSignature,
    OutcomeKind,
    RunningStats,
    SelectionWeights,
    SkillComposer,
    SkillKind,
    SkillLibrary,
    SkillProfile,
    SkillScore,
    SkillSelection,
    SkillSpec,
)
from .associative_memory import (
    AssociationHit,
    AssociationKind,
    AssociationPolicy,
    AssociativeMemoryGameIndex,
    AssociativeMemoryMesh,
    MemoryAssociation,
    SequencePrediction,
)
from .context_acquisition import (
    AcquisitionTrace,
    CueFirstContextSystem,
    InteractionAcquisitionEngine,
    InteractionAcquisitionPolicy,
    RecallTrace,
    build_cue_first_context_system,
)
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
from .context_pipeline import (
    ContextResolution,
    ContextSourceAdapter,
    ContextSourceKind,
    ContextTier,
    LayeredContextCompiler,
    LayeredContextResolver,
    ResolutionPolicy,
    ResolutionStage,
    ResolvedItem,
    SourceRecord,
)
from .cortex import (
    CortexCheckpointAssessment,
    CortexConfig,
    CortexError,
    CortexRunReport,
    JeevesCortex,
    RunCognitiveState,
)
from .epistemic_authorization import (
    AuthorizationAuditEvent,
    AuthorizationError,
    AuthorizationFailure,
    AuthorizationPolicy,
    AuthorizationResult,
    AuthorizationToken,
    DecisionAuthorizer,
    ExecutionPermit,
)
from .epistemic_planning import (
    ActionCandidate,
    BeliefContribution,
    BeliefRequirement,
    CandidateAssessment,
    DecisionDisposition,
    DecisionPolicy,
    EpistemicDecision,
    EpistemicDecisionBridge,
    EpistemicDecisionError,
    ObservationOpportunity,
    RegretRow,
    StressKind,
    StressResult,
    UtilityInterval,
)
from .epistemic_tool_gate import (
    AuthorizedToolDenied,
    AuthorizedToolError,
    BoundToolExecution,
    PermitBoundToolExecutor,
    ToolExecutionIntent,
    bind_intent_metadata,
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
from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditCheckpoint,
    ExecutionAuditEntry,
    ExecutionAuditError,
    ExecutionAuditLedger,
    ExecutionReplayVerifier,
    GENESIS_HASH,
    InMemoryExecutionAuditStore,
    OperationReplay,
    ReplayIssue,
    ReplayIssueKind,
    ReplayReport,
)
from .frontier_control_plane import FrontierCognitiveControlPlane
from .interpretive_science import (
    DomainCalibration,
    JuxtapositionTrial,
    LensOutcomeTrial,
    ScientificLensLab,
    ScientificLensPolicy,
    ScientificLensReport,
    ScientificLensStatus,
)
from .lens_hypergraph import (
    HyperedgeKind,
    HypergraphPolicy,
    LensHyperedge,
    PerpendicularRestartBundle,
    SemanticHypergraphSnapshot,
    SemanticLensHypergraph,
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
from .memory_game import (
    CardHit as MemoryGameCardHit,
    IndexCardStore,
    InteractionCard,
    MemoryGameError,
    MemoryGameIndex,
    MemoryGamePolicy,
    RecallFeedback,
)
from .metacognition import (
    ActionSignals,
    BudgetPressure,
    CognitiveMode,
    EpistemicSignals,
    LoopDetector,
    LoopSignals,
    MetaController,
    MetaCognitionError,
    MetaDecision,
    MetaPolicy,
    MetaReason,
    MetaState,
    MetaStateBuilder,
    ModeScore,
    ProgressSignals,
    RiskSignals,
    action_signals,
    budget_pressure,
    epistemic_signals,
    progress_signals,
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
from .probability_frontier import (
    FrontierProbabilityAssessment,
    FrontierProbabilityLens,
    FrontierProbabilityWorkbench,
    anytime_hoeffding_interval,
    competing_risk_probability,
    conformal_error_bound,
    cvar_failure_probability,
    distribution_shift_bound,
    frechet_joint_bounds,
    generalized_pareto_tail_probability,
    importance_sampling_probability,
    information_directed_score,
    log_opinion_pool,
    model_mixture_probability,
    partial_identification_interval,
    poisson_at_least_one,
    retrieval_competition_probability,
    robust_ambiguity_probability,
    sequential_e_value,
    split_conformal_p_value,
    system_reliability,
    uncertainty_decomposition,
)
from .probability_lenses import (
    AssessmentShape,
    ProbabilityAssessment,
    ProbabilityError,
    ProbabilityLens,
    ProbabilityWorkbench,
    calibrated_forecast_probability,
    dempster_shafer_support,
    empirical_game_probability,
    fair_dice_sum_probability,
    hazard_survival_probability,
    imprecise_probability,
    memory_retrieval_probability,
    possibility_necessity_support,
    transition_probability,
)
from .predictive_fusion import (
    FusedPrediction,
    FusionPolicy,
    PredictiveFusionEngine,
    PredictiveSignal,
    PredictiveSource,
    ReliabilityPosterior,
    SignalAttribution,
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
    JeevesAgentRuntime as LegacyJeevesAgentRuntime,
    RunCheckpoint,
    RunInputs,
)
from .runtime_abstraction import (
    ArgumentAbstractionPolicy,
    ArgumentAbstractor,
    GeneralizingRuntimeEpistemicGuard,
)
from .runtime_guard import (
    GuardAdmissionMode,
    GuardFinalization,
    GuardedToolExecution,
    RiskGuardProfile,
    RuntimeEpistemicGuard,
    RuntimeGuardDenied,
    RuntimeGuardError,
    RuntimeGuardPolicy,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
from .strict_runtime import StrictJeevesAgentRuntime
from .frontier_runtime import (
    FrontierJeevesAgentRuntime,
    HardenedJeevesAgentRuntime,
)
from .semantic_extreme_lenses import (
    LensMaturity,
    RareLensDefinition,
    definitions_by_family,
    rare_semantic_definitions,
    rare_semantic_specs,
    register_rare_lenses,
)
from .semantic_frontier import (
    FrontierLensRouter,
    FrontierSemanticRegistry,
    LensCompositionEngine,
    LensInteraction,
    LensInteractionKind,
    LensInteractionRule,
    SemanticComposition,
    default_interaction_rules,
    frontier_semantic_lenses,
)
from .semantic_maximal import (
    MaximalLensRouter,
    MaximalSemanticRegistry,
    MaximalSemanticRuntime,
    MaximalSemanticSnapshot,
)
from .semantic_lenses import (
    JuxtapositionAnalyzer,
    JuxtapositionSignal,
    LensFamily,
    LensSelection,
    ReadingStatus,
    SemanticFinding,
    SemanticLensRegistry,
    SemanticLensRouter,
    SemanticLensSpec,
    SemanticObservation,
    SemanticRole,
    TangentSeed,
)
from .semantic_prediction import (
    PredictionEvaluation,
    PredictionPolicy,
    PredictionStatus,
    SemanticForecast,
    SemanticPredictionLedger,
    SemanticPredictiveModel,
    log_odds_pool,
)
from .semantic_tangent_bridge import (
    SemanticRestartPacket,
    SemanticTangentBridge,
    TangentBridgePolicy,
)
from .tangent_graph import (
    ExplorationAxis,
    FrontierSelection,
    RestartContinuityBundle,
    TangentGraph,
    TangentNode,
    TangentState,
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
from .uncertainty_frontier import (
    BayesianCategorical,
    DecisionCalibration,
    DependenceDiagnostics,
    FrontierLens,
    FrontierLensContract,
    FrontierLensRegistry,
    FrontierMeasurement,
    FrontierUncertaintyError,
    GameProbability,
    IdentificationDiagnostics,
    ImplementationStatus,
    InfluenceDiagnostics,
    MemoryUncertainty,
    MonteCarloDiagnostics,
    QuantityKind,
    SequentialInference,
    frontier_lens_contracts,
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
from .world_model import (
    BeliefConflict,
    BeliefEdge,
    BeliefGraph,
    BeliefRevision,
    BeliefState,
    BeliefUpdate,
    ContradictionGroup,
    CounterfactualProbe,
    EdgeKind,
    Hypothesis,
    HypothesisStatus,
    Proposition,
    RevisionKind,
    TransactionResult,
    WorldModel,
    WorldModelError,
    WorldSnapshot,
    binary_entropy,
    clamp_probability,
    proposition_from_artifact,
    reliability_to_likelihood_ratio,
)

from .lens_governance import (
    LensGovernanceDecision,
    LensPermission,
    LensScienceProfile,
    LensScienceRegistry,
    ResearchReference,
    ScientificGrade,
    explicit_profiles,
)

from .nuance_runtime import (
    FrontierUncertaintyRouter,
    NuanceFrame,
    NuanceRuntimeError,
    NuanceRuntimePolicy,
    NuanceUpdate,
    ScientificNuanceRuntime,
    UncertaintyRecommendation,
)

# Scientific inference, fast memory, semantic lenses, and context fabric.
from .probability_lenses import (
    AssessmentShape,
    ProbabilityAssessment,
    ProbabilityError,
    ProbabilityLens,
    ProbabilityWorkbench,
    aleatoric_epistemic_assessment,
    bayesian_beta_probability,
    calibrated_forecast_probability,
    causal_interventional_probability,
    conformal_coverage_assessment,
    counterfactual_probability,
    discrete_cvar,
    empirical_game_probability,
    ensemble_model_probability,
    expected_calibration_error,
    expected_information_gain,
    fair_dice_sum_probability,
    frequentist_probability,
    hidden_state_binary_update,
    hypergeometric_probability,
    imprecise_probability,
    likelihood_evidence,
    memory_pair_next_flip_probability,
    memory_retrieval_probability,
    posterior_predictive_probability,
    robust_bayes_envelope,
    surprisal_probability,
    transition_probability,
)
from .lens_system import (
    DirectionLedger,
    LensActivation,
    LensAuthority,
    LensBundle,
    LensCatalog,
    LensDefinition,
    LensFamily,
    PerpendicularDirection,
    SemanticLensRouter,
    default_lenses,
)
from .memory_game_index import (
    CardKind,
    CardRelation,
    IndexCard,
    IndexCardError,
    MemoryGameIndex,
    MemoryGamePolicy,
    RecallHit,
    RecallPacket,
    RelationKind,
    SourceTier,
)
from .context_fabric import (
    CallableContextAdapter,
    CognitiveContextFabric,
    ContextFabricPolicy,
    ContextFabricResult,
    ContextStoreAdapter,
    DeepContextRecord,
    MemoryManagerAdapter,
    RepositoryContextAdapter,
)
from .context_mesh import ContextRepositoryMesh, MultiplexedRepositoryAdapter
from .context_repository import (
    ContextConstitution,
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextRepository,
    ContextRepositoryError,
    ContextSnapshot,
    MergeStrategy,
    PatchOperation,
)
from .predictive_memory import (
    MemoryPrediction,
    PredictionUpdate as MemoryPredictionUpdate,
    PredictiveMemoryEngine,
    PredictiveMemoryPolicy,
    TransitionEstimate,
)
from .historical_synthesis import (
    AnnualFrontier,
    ChronologicalScientificFrontier,
    EvidenceProfile as HistoricalEvidenceProfile,
    HistoricalContextAdapter,
    HistoricalMethod,
    HistoricalReference,
    HistoricalSynthesisPolicy,
    MethodEvaluation,
    MethodFamily,
    MethodScore,
    QualityVector,
    foundational_seed_methods,
)

# Causal inference, Bayesian mechanism learning, and robust cognitive control.
from .causal_epistemics import (
    ActionEvaluation as CausalActionEvaluation,
    ActiveInferencePlanner,
    CategoricalDistribution,
    CausalEpistemicKernel,
    CausalExperimentPlanner,
    CausalMechanism,
    CausalVariable,
    CounterfactualEstimate,
    DecisionRegretAudit,
    ExperimentCandidate,
    InferenceResult as CausalInferenceResult,
    MechanismDriftDetector,
    Preference as CausalPreference,
    SimulationRecord,
    StructuralCausalModel,
    TransitionSample,
)
from .causal_ensemble import (
    BayesianCausalEnsemble,
    CausalModelHypothesis,
    EnsembleExperiment,
    EnsemblePolicy,
    EnsemblePrediction,
    ModelPosterior,
    PosteriorHealth,
    RobustActionEvaluation,
    RobustObjective,
)
from .interventional_learning import (
    BayesianMechanismTrainer,
    DirichletPosterior,
    MechanismTrainingPolicy,
    MechanismTrainingReport,
    PredictiveMetrics,
    promote_training_report,
)
from .causal_inference import (
    EliminationHeuristic,
    Factor,
    FactorCompiler,
    FactorComplexityExceeded,
    FactorInferenceResult,
    InferenceDiagnostics,
    InferencePolicy,
    ScalableCausalView,
    VariableEliminationEngine,
)
from .scalable_causal_ensemble import (
    FactorizedBayesianCausalEnsemble,
    ScalableCausalEnsembleFactory,
)
from .frontier_control_plane import FrontierCognitiveControlPlane

# Multi-level semantic compiler/decompiler and translation validation.
from .semantic_ir import (
    BasicBlock as SemanticBasicBlock,
    Dialect as SemanticDialect,
    Effect as SemanticEffect,
    IRFunction,
    IRModule,
    IRStage,
    IRType,
    IRValidationError,
    OpCode as SemanticOpCode,
    Operation as SemanticOperation,
    SourceOrigin,
    ValueRef,
)
from .compiler_assurance import (
    AnalysisDomain,
    AssurancePolicy,
    CompilerSemanticAssurance,
    FailureReproducer,
    FindingSeverity,
    PassAnalysisDeclaration,
    ProofScope,
    SemanticAssuranceFinding,
    SemanticAssuranceReport,
    STANDARD_REFERENCES as COMPILER_STANDARD_REFERENCES,
)
from .compiler_validation import (
    PassApplication,
    PassContract,
    StageLoweringPass,
    TransactionalPassManager,
    TranslationCounterexample,
    TranslationValidationReport,
    TranslationValidationStatus,
    TranslationValidator,
)
from .semantic_compiler import (
    CompilationArtifact,
    CompilationPolicy,
    ExecutionDialectLoweringPass,
    SemanticCompiler,
)
from .semantic_decompiler import (
    DecompilationLoss,
    DecompilationReport,
    LossKind,
    RecoveredFunction,
    RecoveredOperation,
    RecoveryConfidence,
    RecoveryMapping,
    SemanticDecompiler,
)

# New application code gets the guarded/generalizing runtime by default. The
# pre-enforcement runtime remains explicitly available for compatibility and
# controlled regression comparisons only.
JeevesAgentRuntime = FrontierJeevesAgentRuntime

__all__ = [name for name in globals() if not name.startswith("_")]
