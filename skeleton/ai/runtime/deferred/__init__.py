"""Deferred AI frontier runtime.

This package materializes executable ownership for the 165 volumes that remain
queued by the canonical masterplan continuation frontier.  It never grants
masterplan completion authority.
"""
from .catalog import DEFERRED_165_SPECS, build_registry, volume_ids
from .contracts import CapabilityRegistry, CapabilitySpec, EvidenceReceipt
from .card_systems import AgentCard, CardClaim, CardRegistry, ClaimKind, DatasetCard, EvidenceRef, ModelCard, ToolCard
from .executor import DeferredEffectAuthority, DeferredExecutionError, DeferredExecutionPendingError, DeferredExecutor, DeferredInvocation, ExecutionOutcome, ExecutionReceipt, FailureReceipt
from .lifecycle_safety import (
    CompatibilityAdapter, Deprecation, DeprecationState, DeprecationWindow,
    LegacyConsumer, MigrationEngine, MigrationMode, MigrationPlan,
    MigrationReceipt, MigrationState, MigrationStep, ParityEvidence,
    RetirementDecision, can_remove_adapter, decide_retirement,
)
from .lifecycle_governance import (
    DataRights, EthicsDecision, EthicsReview, ExperimentExposure,
    ExperimentKillSwitch, ExperimentalFeature, LicenseCompatibility,
    LicenseObligation, LicenseRecord, ModelConsumer, ModelDeprecation,
    ModelGovernanceEvidence, ModelLifecycle, ModelRetirement, ModelState,
    ModelTransition, ProviderCutover, ProviderMigration, ProviderParity,
    ResearchBranch, ResearchBranchPolicy, ResearchMergeCandidate, ResearchRisk,
    RetirementEvidence, RightsDecision, Technique, TechniqueRetirement,
    UsageGrant, ethics_decision, experiment_allowed, license_compatibility,
    provider_cutover, research_merge, retirement_complete, retire_model,
    rights_decision, transition_model,
)
from .compute_fabric import (
    BuildFarmArtifact, BuildFarmJob, BuildWorker, DataLocation, EvalWorker,
    EvaluationFarmJob, EvaluationFarmResult, LocalityConstraint,
    ResearchAllocation, ResearchComputeJob, ResearchPriority, ResearchQueue,
    StorageTier, TierMove, TieringPolicy, TransferPlan, aggregate_results,
    allocate_research, build_artifact, plan_transfer, tier_move_valid,
)
from .runtime_resources import (
    CollectivePlacement, DraftToken, DrainState, EvictionPolicy, GPUAllocation,
    GPUInterconnect, GPUMemoryPool, GPUMemoryReservation, GPUPath, KVCacheEntry,
    KVCacheKey, KVCacheLease, ModelEviction, NUMAAffinity, NUMANode,
    NUMAPlacement, PrefixArtifact, PrefixCacheKey, PrefixReuseDecision,
    SpeculativePlan, VerificationStep, collective_path, evict_model, kv_reusable,
    numa_place, prefix_reuse, reserve_gpu, verify_draft,
)
from .tool_governance import (ToolCapability, ToolCompatibility, ToolDependency, ToolDiscoveryResult, ToolEvidence, ToolGraph, ToolHealth, ToolHealthState, ToolManifest, ToolProbe, ToolResultTrust, ToolValidation, discover, tool_compatibility, tool_health, validate_result)
from .effect_workflows import (Compensation, CompensationResult, CompensationStep, EffectAttempt, EffectReceipt, EffectState, SagaDefinition, SagaInstance, SagaTransition, SideEffect, advance_saga, compensation_result, effect_receipt)
from .cognitive_tools import (CompositionResult, CognitiveStrategy, PlanAnalysis, PlanDiagnostic, PlanLintRule, PlanSimulation, ReasoningCost, ReasoningStage, SimulationFinding, SimulatedStep, StrategyConstraint, StrategyDecision, StrategyEvidence, StrategySelection, StrategyVersion, ToolBinding, ToolComposition, attribute_cost, analyze_plan, compose_tools, production_eligible, select_strategy, simulate_plan)\nfrom .claim_governance import (ClaimFingerprint, ClaimCluster, ClaimMerge, ClaimScope, ClaimValidity, DiversityScore, EvidenceIndependence, ExpirationPolicy, KnowledgeConflict, KnowledgeDiff, KnowledgeSnapshot, KnowledgeSnapshotDigest, ReconciliationCase, ReconciliationDecision, RevalidationRequest, ScopeCompatibility, ScopeDimension, SourceCluster, claim_validity, diversity, merge_claims, reconcile, restore_allowed, scope_compatibility)\nfrom .retrieval_lifecycle import (DataSLO, DataServiceHealth, EmbeddingMigration, EmbeddingRecord, EmbeddingVersion, FreshnessDecision, FreshnessRequirement, FreshnessSLI, FreshnessState, IndexLifecycle, IndexMigration, IndexValidation, IndexWatermark, SearchIndex, SourceIdentity, SourceTrust, StaleAction, TrustEvidence, VectorIndexVersion, comparable, content_role, data_health, freshness, promote_index, retire_index, trust_for)\nfrom .sdk_data import (BenchmarkExecution, BenchmarkManifest, BenchmarkPlugin, Consistency, DataConsumer, DataContract, DataField, EvaluationResult, EvaluationSDK, EventConsumer, EventPublisher, EventSDK, InternalSDK, ProviderAdapterSpec, ProviderConformance, ProviderSDK, SDKCompatibility, SDKExport, Scorer, StateClass, StorageSDK, StoreHandle, TransactionHandle, admit_benchmark, breaking_change, event_compatible, provider_conformant, record_evaluation, select_store, supported_export)\nfrom .build_generation import (BenchmarkExecution, BenchmarkManifest, BenchmarkPlugin, ChangeGate, ChangeRisk, ChangeStep, ClientSDK, ExtensionPoint, GeneratedCode, GenerationSpec, ImpactEvidence, ImpactQuery, ImpactSet, RebuildEvidence, RebuildPlan, RebuildStep, RiskCalibration, RiskFactor, SDKMethod, SDKVersion, SafeChangePlan, SystemArtifact, SystemCompilePlan, SystemSource, change_admissible, compile_system, estimate_risk, generate_client, generate_code, impact, rebuild_admissible, rebuild_verified)\nfrom .intent_resources import (ApprovalBurden, ApprovalReusePolicy, ApprovalScope, ArtifactDependency, ArtifactGraph, ArtifactNode, CalibrationObservation, DependencyKind, HumanFactorFinding, HumanFactorRequirement, IntentConstraint, IntentRevision, OperatorTask, ProjectFact, ProjectMemory, ProjectMemoryRevision, ResolutionReceipt, ResourceHandle, ResourceName, ResourceNamespace, ResourceQuery, ResourceRef, TrustPresentation, TrustSignal, UserIntent, Workspace, WorkspaceMember, WorkspaceResource, artifact_cycle, latest_intent, member_authorized, present_trust, read_project_memory, resolve, reusable)\nfrom .scheduling_autonomy import (Assignment, AutonomyController, AutonomyEscalation, ControlSignal, ControlState, CriticalPath, EscalationEvidence, EscalationGrant, PathBlocker, Schedule, SchedulingPolicy, SchedulingSimulation, Subtask, TaskDecomposition, TaskDependency, TaskSlack, SimulationMetric, WorkloadTrace, control, critical_path, grant_escalation, schedule_ready, validate_decomposition)\nfrom .workflow_tasks import (Assignment, CompiledWorkflow, CompileResult, ComplexityEstimate, ComplexityFeature, DSLDiagnostic, DSLVersion, EstimateRevision, StateMapping, TaskClassification, TaskProfile, TaskType, WorkflowBinding, WorkflowCompatibility, WorkflowLink, WorkflowMigration, WorkflowMigrationReceipt, WorkflowSource, WorkflowVersion, classify, compile_workflow, migrate, rebind, revise, validate_source)\nfrom .control_plane import (Constraint, ConstraintResult, ConstraintSet, ConstraintStrength, ControlPlaneCommand, ControlPlaneReceipt, ControlPlaneState, Decision, DecisionContext, DecisionEdge, DecisionOption, DecisionOutcome, DecisionRecord, NormalizedObjective, Objective, ObjectiveAmbiguity, ObjectiveAssumption, ObjectiveCriterion, ObjectiveState, WorkflowEdge, WorkflowIR, WorkflowNode, apply_command, decide, evaluate_constraints)\nfrom .replay_foundations import (BulkheadLimit, Bulkhead, OverflowDecision, overflow, DeadLetter, ReplayAuthorization, DeadLetterDisposition, dead_letter_disposition, ReplayMode, ReplayRequest, ReplayResult, replay, DeterminismClass, VariancePolicy, DeterminismEnvelope, Instant, Duration, Deadline, IdentifierKind, Identifier, IdentifierCodec, SequenceNumber, LogicalClock, CausalRelation, compare_sequence)\nfrom .reliability_controls import (PressureLevel, BufferLimit, BackpressureSignal, PressureDecision, pressure, WorkClass, LoadShedPolicy, ShedDecision, shed, QueueBudget, CongestionState, QueueKind, QueueDecision, queue_decision, FailureClass, RetryBudget, RetryAttempt, RetryDecision, retry, BreakerState, CircuitBreaker, ProbeResult, BreakerDecision, breaker)\nfrom .safe_operations import (SafeRepairPlan, RepairCheckpoint, RepairEvidence, admit_repair_completion, TwinObservation, DigitalTwin, TwinScenario, DeploymentConstraint, DeploymentProposal, DeploymentSequence, plan_deployment, ResourceRequest, ResourceLease, PlacementDecision, place, QueueShare, StarvationSignal, FairnessPolicy, FairnessDecision, fairness)\nfrom .recovery_diagnostics import (RecoveryArtifact, BootstrapRecovery, BootstrapReceipt, validate_recovery, CrashContext, CrashSignature, CrashReport, SupportRedaction, SupportManifest, SupportBundle, FindingState, DoctorCheck, DoctorFinding, DoctorReport, RepairRequest, HealthEvidence, FaultHypothesis, SelfDiagnostic)\nfrom .identity_operations import (FederationConfig, IdentityClaim, FederatedIdentity, map_identity, AdminPolicy, AdminAction, AdminReceipt, authorize_admin, AuditEntry, AuditQuery, AuditView, project_audit, TelemetryState, OpsMetric, OpsAlert, OperationsDashboard, AgentOpsAlert, AgentOpsView, AgentControlAction, project_agent_ops)\nfrom .supply_chain import (BuildInput, HermeticPolicy, HermeticBuild, CachePolicy, BuildCacheKey, CachedArtifact, BuildIdentity, ArtifactSignature, BinaryAttestation, verify_attestation, InstallerSecurityPolicy, InstallPath, InstallVerification, VersionFloor, UpdateSignature, UpdateMetadata, admit_update)\nfrom .machine_governance import (ReviewOwner, CodeownersRule, SensitiveOwnership, CodeownersManifest, DocReference, DocumentationRule, DocCheck, DiagramSource, DiagramSpec, DiagramArtifact, ArchitectureSnapshot, ArchitectureDiff, diff_architecture, ReproBuild, BuildVariance, ArtifactComparison, compare_builds)\nfrom .repository_governance import (Confidence, LegacyArtifact, IntentHypothesis, ArchaeologyFinding, CustodyMapping, ConsolidationPlan, ConsolidationEvidence, can_retire_source, OriginKind, CodeOrigin, CodeArtifact, CodeTransformation, DuplicateKind, DuplicationFinding, ConvergenceProposal, OwnershipZone, ModuleOwner, OwnershipTransfer, resolve_owner)\nfrom .epistemic_integrity import (ValidityInterval, TemporalClaim, KnowledgeRevision, TemporalKnowledge, HypothesisStatus, EvidenceDirection, Hypothesis, HypothesisEvidence, HypothesisEngine, CausalMethod, CausalClaim, CausalGraph, InterventionResult)\nfrom .contract_fuzzing import ContractFuzzer, FuzzBudget, FuzzFailure, FuzzReport
from .simulation_mode import SimulationAuthority, SimulationEvidence, SimulationRequest, SimulationResult, SimulationRuntime
from .journal import DeferredExecutionJournal, DeferredJournalConflict, DeferredJournalError, DeferredJournalRecord, SqliteDeferredExecutionJournal
from .operational_health import DependencyHealth, DependencyKind, DependencyRisk, FailoverDecision, HealthBlocker, HealthDimension, HealthScorecard, HealthState, ProviderDependency, ProviderHealth, ProviderOutcome, ProviderProfile, ProviderRisk, decide_failover
__all__ = ["AgentCard","CardClaim","CardRegistry","ClaimKind","CapabilityRegistry","CapabilitySpec","ContractFuzzer","FuzzBudget","FuzzFailure","FuzzReport","DEFERRED_165_SPECS","DatasetCard","DeferredEffectAuthority","DeferredExecutionError","DeferredExecutionJournal","DeferredExecutionPendingError","DeferredExecutor","DeferredJournalConflict","DeferredJournalError","DeferredJournalRecord","DeferredInvocation","EvidenceRef","EvidenceReceipt","ExecutionOutcome","ExecutionReceipt","FailureReceipt","ModelCard","SimulationAuthority","SimulationEvidence","SimulationRequest","SimulationResult","SimulationRuntime","SqliteDeferredExecutionJournal","ToolCard","build_registry","volume_ids","DependencyHealth","DependencyKind","DependencyRisk","FailoverDecision","HealthBlocker","HealthDimension","HealthScorecard","HealthState","ProviderDependency","ProviderHealth","ProviderOutcome","ProviderProfile","ProviderRisk","decide_failover"]

from .policy_refresh import (
    KnowledgeRefresh, MemoryPolicy, MemoryPromotion, MemoryRetention, MemoryTrust,
    ProviderCandidate, RankingPolicy, RefreshCoordinator, RefreshCursor,
    RefreshReceipt, RefreshState, RetrievalDocument, RetrievalFilter,
    RetrievalPolicy, RouteConstraint, RouteDecision, RoutingPolicy, retrieve, route,
)

from .model_instruction_ops import (
    EvidenceState, ResearchFindingView, ResearchGap, ResearchDashboard,
    ModelDeployment, ModelHealth, ModelOpsDecision, decide_promotion,
    ModelVersionFence, ModelRollbackPlan, ModelRollbackReceipt,
    InstructionVersion, InstructionAsset, InstructionBinding, bind_instruction,
    PromptBaseline, PromptTest, PromptRegression, evaluate_prompt,
)
