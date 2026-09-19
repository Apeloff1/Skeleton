"""Skeleton shell execution plane.

The package exposes policy-bound argv-only process execution plus the control,
evidence, scheduling, and orchestration primitives used around that boundary.
"""

from skeleton.shells.admission import AdmissionDecision, CommandAdmission
from skeleton.shells.arguments import ArgumentPolicy, ArgumentPolicySet, OptionRule, ValueConstraint
from skeleton.shells.audit import AuditEvent, CompositeAuditSink, JsonlAuditSink, MemoryAuditSink, NullAuditSink, RedactingAuditSink
from skeleton.shells.batch import BatchExecutor, BatchItem, BatchResult
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.circuit import CircuitBreaker, CircuitPolicy, CircuitRegistry, CircuitSnapshot, CircuitState
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.control_plane import ControlPlaneDecision, ShellControlPlane
from skeleton.shells.dedupe import DedupeConflict, DedupeRecord, DedupeRegistry
from skeleton.shells.durable_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptHead,
    ReceiptInclusion,
    ReceiptIndexEntry,
)
from skeleton.shells.evidence_chain import ContentAddressedEvidenceChain, EvidenceConflict, EvidenceCorruption, EvidenceHead, EvidenceNode, EvidenceStateBackend, GENESIS_HASH
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.errors import (
    ArgumentRejected,
    CapabilityDenied,
    CircuitOpen,
    EnvironmentRejected,
    PipelineError,
    SessionBudgetExhausted,
    ShellErrorCode,
    ShellErrorContext,
    ShellPlaneError,
    WorkspaceRejected,
)
from skeleton.shells.executor import ExecutionOutcome, ExecutorConfig, ShellExecutor
from skeleton.shells.explain import CommandExplanation, explain_command
from skeleton.shells.failure import FailureClassification, FailureKind, classify_result
from skeleton.shells.health import HealthFinding, ShellHealthReport, inspect_policy
from skeleton.shells.history import HistoryQuery, ReceiptHistory
from skeleton.shells.hooks import ExecutionMetadata, HookRegistry
from skeleton.shells.leases import Lease, LeaseConflict, LeaseRegistry
from skeleton.shells.limits import ResourceBudget, ResourceLimits, ResourceUsage
from skeleton.shells.manifest import MANIFEST_SCHEMA_VERSION, ManifestError, ManifestLimits, manifest_dict, parse_manifest
from skeleton.shells.output import OutputView, combined_summary, render_output
from skeleton.shells.model import (
    CommandIdentity,
    CommandIntent,
    ExecutionClass,
    ExecutionSummary,
    ExecutionTiming,
    Outcome,
    ResourceRequest,
    ShellInvocation,
    ShellModelError,
    StreamDisposition,
    digest_payload,
    invocation_from_dict,
)
from skeleton.shells.pipeline import (
    PipelineExecutor,
    PipelineResult,
    PipelineSpec,
    PipelineStep,
    PipelineStepResult,
    StepState,
    pipeline_from_commands,
)
from skeleton.shells.policy import intersect_policies, is_narrower_or_equal, narrow_policy
from skeleton.shells.policy_diff import PolicyChange, PolicyDiff, diff_policies
from skeleton.shells.preflight import PreflightAnalyzer, PreflightItem, PreflightReport
from skeleton.shells.profiles import PolicyProfile, PolicyProfileCatalog, build_default_profiles
from skeleton.shells.provenance import (
    canonical_json,
    command_fingerprint,
    digest_arguments,
    digest_environment_keys,
    digest_mapping,
    digest_path,
    policy_fingerprint,
    sha256_hex,
)
from skeleton.shells.queue import QueueItem, QueueState, ShellWorkQueue
from skeleton.shells.rate_limit import RateLimitDecision, RateLimitPolicy, RateLimiter, TokenBucket
from skeleton.shells.receipts import ChainedReceipt, ExecutionReceipt, ReceiptChain
from skeleton.shells.redaction import RedactionPolicy, RedactionRule, SecretRedactor
from skeleton.shells.registry import ExecutableRegistry, ExecutableSpec, RegistrySnapshot
from skeleton.shells.retry import RetryDecision, RetryPolicy
from skeleton.shells.runner import ShellCommand, ShellExecutionError, ShellPolicy, ShellPolicyError, ShellResult, ShellRunner
from skeleton.shells.serialization import SerializationError, dumps, loads_object, receipt_from_dict
from skeleton.shells.session import SessionSnapshot, ShellSession
from skeleton.shells.status import ShellPlaneStatus, status_snapshot
from skeleton.shells.telemetry import CommandMetrics, ShellTelemetry
from skeleton.shells.templates import CommandTemplate, TemplateCatalog, TemplateSlot
from skeleton.shells.tool_adapter import ShellToolAdapter, ToolExecutionRequest, ToolExecutionResponse
from skeleton.shells.workspace import WorkspacePolicy
from skeleton.shells.worker import (
    DrainReport,
    QueueWorker,
    WorkDisposition,
    WorkResult,
    WorkerCounters,
    WorkerGroup,
    WorkerGroupSnapshot,
    WorkerPolicy,
    WorkerSnapshot,
    WorkerState,
)

__all__ = [
    "DistributedReceiptChain",
    "DistributedReceiptConflict",
    "DistributedReceiptCorruption",
    "DistributedReceiptHead",
    "ReceiptInclusion",
    "ReceiptIndexEntry",
    "ContentAddressedEvidenceChain",
    "EvidenceConflict",
    "EvidenceCorruption",
    "EvidenceHead",
    "EvidenceNode",
    "EvidenceStateBackend",
    "GENESIS_HASH",
    "AdmissionDecision", "ArgumentPolicy", "ArgumentPolicySet", "ArgumentRejected", "AuditEvent",
    "BatchExecutor", "BatchItem", "BatchResult", "CapabilityDenied", "CapabilityGrant", "ChainedReceipt",
    "CircuitBreaker", "CircuitOpen", "CircuitPolicy", "CircuitRegistry", "CircuitSnapshot", "CircuitState",
    "CommandAdmission", "CommandCatalog", "CommandDefinition", "CommandExplanation", "CommandMetrics",
    "CommandTemplate", "CompositeAuditSink", "ControlPlaneDecision", "DedupeConflict", "DedupeRecord",
    "DedupeRegistry", "EnvironmentPolicy", "EnvironmentRejected", "EnvironmentValueRule", "ExecutableRegistry",
    "ExecutableSpec", "ExecutionMetadata", "ExecutionOutcome", "ExecutionReceipt", "ExecutorConfig",
    "FailureClassification", "FailureKind", "HealthFinding", "HistoryQuery", "HookRegistry", "JsonlAuditSink",
    "Lease", "LeaseConflict", "LeaseRegistry", "MANIFEST_SCHEMA_VERSION", "ManifestError", "ManifestLimits",
    "MemoryAuditSink", "NullAuditSink", "OptionRule", "OutputView", "PipelineError", "PipelineExecutor",
    "PipelineResult", "PipelineSpec", "PipelineStep", "PipelineStepResult", "PolicyChange", "PolicyDiff",
    "PolicyProfile", "PolicyProfileCatalog", "PreflightAnalyzer", "PreflightItem", "PreflightReport", "QueueItem",
    "QueueState", "RateLimitDecision", "RateLimitPolicy", "RateLimiter", "ReceiptChain", "ReceiptHistory",
    "RedactingAuditSink", "RedactionPolicy", "RedactionRule", "RegistrySnapshot", "ResourceBudget", "ResourceLimits",
    "ResourceUsage", "RetryDecision", "RetryPolicy", "SecretRedactor", "SerializationError", "SessionBudgetExhausted",
    "SessionSnapshot", "ShellCapability", "ShellCommand", "ShellControlPlane", "ShellErrorCode", "ShellErrorContext",
    "ShellExecutionError", "ShellExecutor", "ShellHealthReport", "ShellPlaneError", "ShellPlaneStatus", "ShellPolicy",
    "ShellPolicyError", "ShellResult", "ShellRunner", "ShellSession", "ShellTelemetry", "ShellToolAdapter",
    "ShellWorkQueue", "StepState", "TemplateCatalog", "TemplateSlot", "TokenBucket", "ToolExecutionRequest",
    "ToolExecutionResponse", "ValueConstraint", "WorkspacePolicy", "WorkspaceRejected", "build_default_profiles",
    "canonical_json", "classify_result", "combined_summary", "command_fingerprint", "diff_policies", "digest_arguments",
    "digest_environment_keys", "digest_mapping", "digest_path", "dumps", "explain_command", "inspect_policy",
    "intersect_policies", "is_narrower_or_equal", "loads_object", "manifest_dict", "narrow_policy", "parse_manifest",
    "pipeline_from_commands", "policy_fingerprint", "receipt_from_dict", "render_output", "sha256_hex", "status_snapshot",
]

# Public model/worker surfaces are appended separately to keep the established
# shell-plane export list stable for downstream import-drift checks.
__all__ += [
    "CommandIdentity", "CommandIntent", "ExecutionClass", "ExecutionSummary", "ExecutionTiming",
    "Outcome", "ResourceRequest", "ShellInvocation", "ShellModelError", "StreamDisposition",
    "digest_payload", "invocation_from_dict", "DrainReport", "QueueWorker", "WorkDisposition",
    "WorkResult", "WorkerCounters", "WorkerGroup", "WorkerGroupSnapshot", "WorkerPolicy",
    "WorkerSnapshot", "WorkerState",
]
