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
from .tool_governance import (
    ToolCapability, ToolCompatibility, ToolDependency, ToolDiscoveryResult,
    ToolEvidence, ToolGraph, ToolHealth, ToolHealthState, ToolManifest, ToolProbe,
    ToolResultTrust, ToolValidation, discover, tool_compatibility, tool_health,
    validate_result,
)
from .effect_workflows import (
    Compensation, CompensationResult, CompensationStep, EffectAttempt,
    EffectReceipt, EffectState, SagaDefinition, SagaInstance, SagaTransition,
    SideEffect, advance_saga, compensation_result, effect_receipt,
)
from .contract_fuzzing import ContractFuzzer, FuzzBudget, FuzzFailure, FuzzReport
from .simulation_mode import SimulationAuthority, SimulationEvidence, SimulationRequest, SimulationResult, SimulationRuntime
from .journal import DeferredExecutionJournal, DeferredJournalConflict, DeferredJournalError, DeferredJournalRecord, SqliteDeferredExecutionJournal
from .operational_health import DependencyHealth, DependencyKind, DependencyRisk, FailoverDecision, HealthBlocker, HealthDimension, HealthScorecard, HealthState, ProviderDependency, ProviderHealth, ProviderOutcome, ProviderProfile, ProviderRisk, decide_failover
__all__ = ["AgentCard","CardClaim","CardRegistry","ClaimKind","CapabilityRegistry","CapabilitySpec","ContractFuzzer","FuzzBudget","FuzzFailure","FuzzReport","DEFERRED_165_SPECS","DatasetCard","DeferredEffectAuthority","DeferredExecutionError","DeferredExecutionJournal","DeferredExecutionPendingError","DeferredExecutor","DeferredJournalConflict","DeferredJournalError","DeferredJournalRecord","DeferredInvocation","EvidenceRef","EvidenceReceipt","ExecutionOutcome","ExecutionReceipt","FailureReceipt","ModelCard","SimulationAuthority","SimulationEvidence","SimulationRequest","SimulationResult","SimulationRuntime","SqliteDeferredExecutionJournal","ToolCard","build_registry","volume_ids","DependencyHealth","DependencyKind","DependencyRisk","FailoverDecision","HealthBlocker","HealthDimension","HealthScorecard","HealthState","ProviderDependency","ProviderHealth","ProviderOutcome","ProviderProfile","ProviderRisk","decide_failover"]
