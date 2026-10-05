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

from .identity_operations import (
    AdminAction, AdminPolicy, AdminReceipt, AgentControlAction, AgentOpsAlert,
    AgentOpsView, AuditEntry, AuditQuery, AuditView, FederatedIdentity,
    FederationConfig, IdentityClaim, OperationsDashboard, OpsAlert, OpsMetric,
    TelemetryState, authorize_admin, map_identity, project_agent_ops, project_audit,
)
from .contract_fuzzing import ContractFuzzer, FuzzBudget, FuzzFailure, FuzzReport
from .simulation_mode import SimulationAuthority, SimulationEvidence, SimulationRequest, SimulationResult, SimulationRuntime
from .journal import DeferredExecutionJournal, DeferredJournalConflict, DeferredJournalError, DeferredJournalRecord, SqliteDeferredExecutionJournal
from .operational_health import DependencyHealth, DependencyKind, DependencyRisk, FailoverDecision, HealthBlocker, HealthDimension, HealthScorecard, HealthState, ProviderDependency, ProviderHealth, ProviderOutcome, ProviderProfile, ProviderRisk, decide_failover
__all__ = ["AgentCard","CardClaim","CardRegistry","ClaimKind","CapabilityRegistry","CapabilitySpec","ContractFuzzer","FuzzBudget","FuzzFailure","FuzzReport","DEFERRED_165_SPECS","DatasetCard","DeferredEffectAuthority","DeferredExecutionError","DeferredExecutionJournal","DeferredExecutionPendingError","DeferredExecutor","DeferredJournalConflict","DeferredJournalError","DeferredJournalRecord","DeferredInvocation","EvidenceRef","EvidenceReceipt","ExecutionOutcome","ExecutionReceipt","FailureReceipt","ModelCard","SimulationAuthority","SimulationEvidence","SimulationRequest","SimulationResult","SimulationRuntime","SqliteDeferredExecutionJournal","ToolCard","build_registry","volume_ids","DependencyHealth","DependencyKind","DependencyRisk","FailoverDecision","HealthBlocker","HealthDimension","HealthScorecard","HealthState","ProviderDependency","ProviderHealth","ProviderOutcome","ProviderProfile","ProviderRisk","decide_failover"]
