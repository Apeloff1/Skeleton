"""Skeleton agent orchestration primitives."""

from skeleton.automation.agents.mesh import AgentMesh

from skeleton.automation.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
from skeleton.automation.agents.delegation_qualification import (
    AGENT_DELEGATION_ACCOUNTABILITY_ID,
    AGENT_DELEGATION_SCHEMA_VERSION,
    AGENT_DELEGATION_TASK_ID,
    AgentDelegationAuthority,
    AgentDelegationDecision,
    AgentDelegationError,
    DelegationBudget,
    qualify_agent_delegation,
)
from skeleton.automation.agents.autonomy_control import (
    AUTONOMY_CONTROL_ACCOUNTABILITY_ID,
    AUTONOMY_CONTROL_SCHEMA_VERSION,
    AUTONOMY_CONTROL_TASK_ID,
    AutonomyAuthorization,
    AutonomyControlError,
    AutonomyLevel,
    AutonomyPolicy,
    AutonomySignal,
    AutonomyState,
    AutonomyTransitionDecision,
    TransitionDisposition,
    evaluate_autonomy_transition,
)
from skeleton.automation.agents.human_control import (
    HUMAN_CONTROL_ACCOUNTABILITY_ID,
    HUMAN_CONTROL_SCHEMA_VERSION,
    HUMAN_CONTROL_TASK_ID,
    HumanControlAction,
    HumanControlCommand,
    HumanControlDecision,
    HumanControlError,
    HumanControlState,
    evaluate_human_control,
)
from skeleton.automation.agents.blast_radius import (
    BLAST_RADIUS_ACCOUNTABILITY_ID,
    BLAST_RADIUS_SCHEMA_VERSION,
    BLAST_RADIUS_TASK_ID,
    ActionRiskProfile,
    AdversarialAlignmentReport,
    BlastRadiusDecision,
    BlastRadiusError,
    BlastRadiusPolicy,
    ImpactClass,
    ReversibilityClass,
    classify_impact,
    qualify_blast_radius,
)
from skeleton.automation.agents.safe_autonomy import (
    SAFE_AUTONOMY_ACCOUNTABILITY_ID,
    SAFE_AUTONOMY_SCHEMA_VERSION,
    SAFE_AUTONOMY_TASK_ID,
    SafeAutonomyDecision,
    SafeAutonomyError,
    qualify_safe_autonomy,
)
from skeleton.automation.agents.bridge import MeshBridge
from skeleton.automation.agents.swarm_admission import AdmissionDecision, AdmissionPolicy, capability_coverage
from skeleton.automation.agents.swarm_autoscale import AutoscalePolicy, ScaleRecommendation
from skeleton.automation.agents.swarm_broker import BrokerResult, CompletionResult, SwarmBroker
from skeleton.automation.agents.swarm_checkpoint import Checkpoint, CheckpointStore
from skeleton.automation.agents.swarm_control import SubmitResult, SwarmControlPlane
from skeleton.automation.agents.swarm_dedupe import Completion, CompletionCache
from skeleton.automation.agents.swarm_drain import DrainPlan, drain, plan_drain
from skeleton.automation.agents.swarm_exact_lease import lease_exact
from skeleton.automation.agents.swarm_fairness import FairShareLedger, TenantShare
from skeleton.automation.agents.swarm_fencing import LeaseFence, assert_fence, fence_for, fenced_fail, fenced_renew, fenced_succeed
from skeleton.automation.agents.swarm_gc import GCResult, capacity, compact_runtime as gc_compact_runtime
from skeleton.automation.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.automation.agents.swarm_idempotency import IdempotencyConflict, IdempotencyRecord, IdempotencyRegistry
from skeleton.automation.agents.swarm_ingress import IngressDecision, SwarmIngressGovernor
from skeleton.automation.agents.swarm_invariants import InvariantReport, audit
from skeleton.automation.agents.swarm_janitor import JanitorResult, reap_stale_workers
from skeleton.automation.agents.swarm_load_shed import LoadShedPolicy, ShedDecision
from skeleton.automation.agents.swarm_maintenance import compact_runtime, compact_state
from skeleton.automation.agents.swarm_operator import SwarmOperator
from skeleton.automation.agents.swarm_pressure import PressureReport, classify_pressure
from skeleton.automation.agents.swarm_quarantine import QuarantineController, QuarantineRecord
from skeleton.automation.agents.swarm_queries import TaskPage, query_tasks
from skeleton.automation.agents.swarm_quota import Quota, QuotaExceeded, QuotaLedger, Usage
from skeleton.automation.agents.swarm_rate_limit import Bucket, TokenBucketLimiter
from skeleton.automation.agents.swarm_recovery import (
    MAX_RECOVERY_ARCHIVE_BYTES,
    RECOVERY_ARCHIVE_VERSION,
    RecoveryStatus,
    SwarmRecoveryManager,
)
from skeleton.automation.agents.swarm_resilient_scheduler import ResilientRanking, ResilientSwarmScheduler
from skeleton.automation.agents.swarm_restore import validate_restore_state
from skeleton.automation.agents.swarm_retention import PrunePlan, RetentionPolicy, TERMINAL_STATES
from skeleton.automation.agents.swarm_retry import RetryDecision, RetryPolicy
from skeleton.automation.agents.swarm_scheduler import SwarmScheduler, WorkerScore
from skeleton.automation.agents.swarm_slo import SLOPolicy
from skeleton.automation.agents.swarm_snapshot import CURRENT_VERSION, SnapshotError, normalize_snapshot, validate_snapshot
from skeleton.automation.agents.swarm_supervisor import DispatchDecision, SwarmSupervisor
from skeleton.automation.agents.swarm_tenant_broker import TenantBrokerResult, TenantRepairResult, TenantSwarmBroker
from skeleton.automation.agents.swarm_tenant_checkpoint import TenantCheckpointStore, TenantMetadataCheckpoint
from skeleton.automation.agents.swarm_runtime import AdmissionError, LeaseError, RuntimeSnapshot, SwarmRuntime, SwarmTask, TaskState, WorkerState

__all__ = [
    "AgentMesh",
    "Coordinator", "AgentPool", "Task", "TaskStatus", "MeshBridge",
    "AUTONOMY_CONTROL_ACCOUNTABILITY_ID", "AUTONOMY_CONTROL_SCHEMA_VERSION",
    "AUTONOMY_CONTROL_TASK_ID", "AutonomyAuthorization", "AutonomyControlError",
    "AutonomyLevel", "AutonomyPolicy", "AutonomySignal", "AutonomyState",
    "AutonomyTransitionDecision", "TransitionDisposition", "evaluate_autonomy_transition",
    "HUMAN_CONTROL_ACCOUNTABILITY_ID", "HUMAN_CONTROL_SCHEMA_VERSION",
    "HUMAN_CONTROL_TASK_ID", "HumanControlAction", "HumanControlCommand",
    "HumanControlDecision", "HumanControlError", "HumanControlState",
    "evaluate_human_control",
    "BLAST_RADIUS_ACCOUNTABILITY_ID", "BLAST_RADIUS_SCHEMA_VERSION",
    "BLAST_RADIUS_TASK_ID", "ActionRiskProfile", "AdversarialAlignmentReport",
    "BlastRadiusDecision", "BlastRadiusError", "BlastRadiusPolicy", "ImpactClass",
    "ReversibilityClass", "classify_impact", "qualify_blast_radius",
    "SAFE_AUTONOMY_ACCOUNTABILITY_ID", "SAFE_AUTONOMY_SCHEMA_VERSION",
    "SAFE_AUTONOMY_TASK_ID", "SafeAutonomyDecision", "SafeAutonomyError",
    "qualify_safe_autonomy",
    "AGENT_DELEGATION_ACCOUNTABILITY_ID", "AGENT_DELEGATION_SCHEMA_VERSION",
    "AGENT_DELEGATION_TASK_ID", "AgentDelegationAuthority", "AgentDelegationDecision",
    "AgentDelegationError", "DelegationBudget", "qualify_agent_delegation",
    "AdmissionError", "LeaseError", "RuntimeSnapshot", "SwarmRuntime", "HardenedSwarmRuntime",
    "SwarmTask", "TaskState", "WorkerState", "AdmissionDecision", "AdmissionPolicy",
    "capability_coverage", "AutoscalePolicy", "ScaleRecommendation", "BrokerResult", "CompletionResult",
    "SwarmBroker", "Checkpoint", "CheckpointStore", "SubmitResult", "SwarmControlPlane", "Completion",
    "CompletionCache", "DrainPlan", "drain", "plan_drain", "lease_exact", "FairShareLedger", "TenantShare",
    "LeaseFence", "assert_fence", "fence_for", "fenced_fail", "fenced_renew", "fenced_succeed", "GCResult",
    "capacity", "gc_compact_runtime", "IdempotencyConflict", "IdempotencyRecord", "IdempotencyRegistry",
    "IngressDecision", "SwarmIngressGovernor", "InvariantReport", "audit", "JanitorResult", "reap_stale_workers",
    "LoadShedPolicy", "ShedDecision", "compact_runtime", "compact_state", "SwarmOperator", "PressureReport",
    "classify_pressure", "QuarantineController", "QuarantineRecord", "TaskPage", "query_tasks", "Quota",
    "QuotaExceeded", "QuotaLedger", "Usage", "Bucket", "TokenBucketLimiter", "RecoveryStatus",
    "SwarmRecoveryManager", "RECOVERY_ARCHIVE_VERSION", "MAX_RECOVERY_ARCHIVE_BYTES",
    "ResilientRanking", "ResilientSwarmScheduler", "validate_restore_state",
    "PrunePlan", "RetentionPolicy", "TERMINAL_STATES", "RetryDecision", "RetryPolicy", "SwarmScheduler",
    "WorkerScore", "SLOPolicy", "CURRENT_VERSION", "SnapshotError", "normalize_snapshot",
    "validate_snapshot", "DispatchDecision", "SwarmSupervisor", "TenantBrokerResult", "TenantRepairResult",
    "TenantSwarmBroker", "TenantCheckpointStore", "TenantMetadataCheckpoint",
]
