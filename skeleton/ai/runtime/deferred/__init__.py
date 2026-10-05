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
from .cognitive_tools import (CompositionResult, CognitiveStrategy, PlanAnalysis, PlanDiagnostic, PlanLintRule, PlanSimulation, ReasoningCost, ReasoningStage, SimulationFinding, SimulatedStep, StrategyConstraint, StrategyDecision, StrategyEvidence, StrategySelection, StrategyVersion, ToolBinding, ToolComposition, attribute_cost, analyze_plan, compose_tools, production_eligible, select_strategy, simulate_plan)\nfrom .claim_governance import (ClaimFingerprint, ClaimCluster, ClaimMerge, ClaimScope, ClaimValidity, DiversityScore, EvidenceIndependence, ExpirationPolicy, KnowledgeConflict, KnowledgeDiff, KnowledgeSnapshot, KnowledgeSnapshotDigest, ReconciliationCase, ReconciliationDecision, RevalidationRequest, ScopeCompatibility, ScopeDimension, SourceCluster, claim_validity, diversity, merge_claims, reconcile, restore_allowed, scope_compatibility)\nfrom .retrieval_lifecycle import (DataSLO, DataServiceHealth, EmbeddingMigration, EmbeddingRecord, EmbeddingVersion, FreshnessDecision, FreshnessRequirement, FreshnessSLI, FreshnessState, IndexLifecycle, IndexMigration, IndexValidation, IndexWatermark, SearchIndex, SourceIdentity, SourceTrust, StaleAction, TrustEvidence, VectorIndexVersion, comparable, content_role, data_health, freshness, promote_index, retire_index, trust_for)\nfrom .contract_fuzzing import ContractFuzzer, FuzzBudget, FuzzFailure, FuzzReport
from .simulation_mode import SimulationAuthority, SimulationEvidence, SimulationRequest, SimulationResult, SimulationRuntime
from .journal import DeferredExecutionJournal, DeferredJournalConflict, DeferredJournalError, DeferredJournalRecord, SqliteDeferredExecutionJournal
from .operational_health import DependencyHealth, DependencyKind, DependencyRisk, FailoverDecision, HealthBlocker, HealthDimension, HealthScorecard, HealthState, ProviderDependency, ProviderHealth, ProviderOutcome, ProviderProfile, ProviderRisk, decide_failover
__all__ = ["AgentCard","CardClaim","CardRegistry","ClaimKind","CapabilityRegistry","CapabilitySpec","ContractFuzzer","FuzzBudget","FuzzFailure","FuzzReport","DEFERRED_165_SPECS","DatasetCard","DeferredEffectAuthority","DeferredExecutionError","DeferredExecutionJournal","DeferredExecutionPendingError","DeferredExecutor","DeferredJournalConflict","DeferredJournalError","DeferredJournalRecord","DeferredInvocation","EvidenceRef","EvidenceReceipt","ExecutionOutcome","ExecutionReceipt","FailureReceipt","ModelCard","SimulationAuthority","SimulationEvidence","SimulationRequest","SimulationResult","SimulationRuntime","SqliteDeferredExecutionJournal","ToolCard","build_registry","volume_ids","DependencyHealth","DependencyKind","DependencyRisk","FailoverDecision","HealthBlocker","HealthDimension","HealthScorecard","HealthState","ProviderDependency","ProviderHealth","ProviderOutcome","ProviderProfile","ProviderRisk","decide_failover"]
