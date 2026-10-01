"""Skeleton persistence package.

Core durable repositories import eagerly. Snapshot compatibility helpers are
loaded lazily because snapshot restoration reaches Jeeves/orchestration
surfaces and therefore belongs to the higher architecture layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skeleton.persistence.conversation_repository import (
    ConversationAuthorizationError,
    ConversationConflict,
    ConversationNotFound,
    ConversationRepositoryCorruption,
    ConversationRepositoryError,
    SQLiteConversationRepository,
)
from skeleton.persistence.execution_repository import (
    ExecutionOutboxEvent,
    ExecutionRepositoryConflict,
    ExecutionRepositoryCorruption,
    ExecutionRepositoryError,
    SQLiteExecutionRepository,
)
from skeleton.persistence.memory_repository import (
    MemoryConflict,
    MemoryNotFound,
    MemoryProjectionEvent,
    MemoryRepositoryError,
    MemoryRevision,
    MongoMemoryRepository,
    SQLiteMemoryRepository,
)
from skeleton.persistence.operation_store import (
    OperationOutboxEvent,
    OperationStoreConflict,
    OperationStoreCorruptionError,
    OperationStoreError,
    SQLiteOperationStore,
    StoredOperation,
)
from skeleton.persistence.operation_runtime import (
    DurableOperationRuntime,
    OutboxDispatchReport,
)
from skeleton.persistence.inbox_ledger import SQLiteInboxLedger
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.spine_projection import SpineProjection, SpineProjectionReport
from skeleton.persistence.spine_land import SpineLand, SpineLandReport
from skeleton.persistence.mongo_inbox import MongoInboxLedger
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.spine_quarantine import SpineQuarantine
from skeleton.persistence.spine_status import SpineStatus
from skeleton.persistence.mongo_projection import MongoSpineProjection, MongoProjectionReport
from skeleton.persistence.spine_repair import SpineRepairPlan
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_catalog import SpineCatalog
from skeleton.persistence.mongo_catalog import MongoCatalog
from skeleton.persistence.spine_batch import SpineBatch, SpineBatchReport
from skeleton.persistence.spine_witness import SpineWitness
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_cutover import SpineCutover
from skeleton.persistence.spine_window import SpineWindow
from skeleton.persistence.spine_seal import SpineSeal
from skeleton.persistence.spine_digest import SpineDigest
from skeleton.persistence.spine_ledger import SpineLedger
from skeleton.persistence.spine_index import SpineIndexPlan
from skeleton.persistence.spine_bind import SpineBind
from skeleton.persistence.spine_tracker import SpineTracker
from skeleton.persistence.spine_pair import SpinePair
from skeleton.persistence.spine_replay import SpineReplay
from skeleton.persistence.spine_sweep import SpineSweep
from skeleton.persistence.spine_export import SpineExport
from skeleton.persistence.spine_hold import SpineHold
from skeleton.persistence.spine_manifest import SpineManifest
from skeleton.persistence.spine_masterplan import SpineMasterplan
from skeleton.persistence.spine_reaccept import SpineReaccept
from skeleton.persistence.spine_gate import SpineGate
from skeleton.persistence.spine_watch import SpineWatch
from skeleton.persistence.spine_gap import SpineGap
from skeleton.persistence.spine_poison_ticket import SpinePoisonTicket
from skeleton.persistence.spine_poison_apply import SpinePoisonApply
from skeleton.persistence.spine_poison_witness import SpinePoisonWitness
from skeleton.persistence.spine_poison_chain import SpinePoisonChain
from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_index_bind import SpineIndexBind
from skeleton.persistence.spine_bind_audit import SpineBindAudit
from skeleton.persistence.spine_cut_gate import SpineCutGate
from skeleton.persistence.spine_surface import SpineSurface
from skeleton.persistence.spine_provider_probe import SpineProviderProbe
from skeleton.persistence.spine_pr_probe import SpinePrProbe
from skeleton.persistence.spine_unread_gap import SpineUnreadGap
from skeleton.persistence.spine_surface_seal import SpineSurfaceSeal
from skeleton.persistence.spine_ci_witness import SpineCiWitness
from skeleton.persistence.spine_merge_gate import SpineMergeGate
from skeleton.persistence.spine_probe_replay import SpineProbeReplay
from skeleton.persistence.spine_motor_witness import SpineMotorWitness
from skeleton.persistence.spine_dispatch_witness import SpineDispatchWitness
from skeleton.persistence.spine_dark import SpineDark
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness
from skeleton.persistence.spine_quiet import SpineQuiet
from skeleton.persistence.spine_quiet_witness import SpineQuietWitness
from skeleton.persistence.spine_bind_card import SpineBindCard
from skeleton.persistence.spine_bind_journal import SpineBindJournal
from skeleton.persistence.spine_bind_read import SpineBindRead
from skeleton.persistence.spine_bind_chain import SpineBindChain
from skeleton.persistence.spine_bind_tenant import SpineBindTenant
from skeleton.persistence.spine_bind_replay import SpineBindReplay
from skeleton.persistence.spine_bind_surface import SpineBindSurface
from skeleton.persistence.spine_bind_gap import SpineBindGap
from skeleton.persistence.spine_bind_snapshot import SpineBindSnapshot
from skeleton.persistence.spine_bind_recovery import SpineBindRecovery
from skeleton.persistence.spine_bind_checkpoint import SpineBindCheckpoint
from skeleton.persistence.spine_bind_checkpoint_replay import SpineBindCheckpointReplay
from skeleton.persistence.spine_bind_checkpoint_tenant import SpineBindCheckpointTenant
from skeleton.persistence.spine_bind_checkpoint_chain import SpineBindCheckpointChain
from skeleton.persistence.spine_bind_bundle import SpineBindBundle
from skeleton.persistence.spine_bind_bundle_verify import SpineBindBundleVerify
from skeleton.persistence.spine_bind_restore_receipt import SpineBindRestoreReceipt
from skeleton.persistence.spine_bind_restore_verify import SpineBindRestoreVerify
from skeleton.persistence.spine_bind_restore_journal import SpineBindRestoreJournal
from skeleton.persistence.spine_bind_restore_replay import SpineBindRestoreReplay
from skeleton.persistence.spine_bind_restore_tenant import SpineBindRestoreTenant
from skeleton.persistence.spine_bind_restore_chain import SpineBindRestoreChain
from skeleton.persistence.spine_bind_restore_continuity import SpineBindRestoreContinuity
from skeleton.persistence.spine_bind_restore_export import SpineBindRestoreExport
from skeleton.persistence.spine_bind_restore_export_verify import SpineBindRestoreExportVerify
from skeleton.persistence.spine_motor_plan import SpineMotorPlan
from skeleton.persistence.spine_motor_bootstrap import SpineMotorBootstrap
from skeleton.persistence.spine_motor_bootstrap_verify import SpineMotorBootstrapVerify
from skeleton.persistence.spine_motor_bootstrap_replay import SpineMotorBootstrapReplay
from skeleton.persistence.spine_motor_preflight import SpineMotorPreflight
from skeleton.persistence.spine_motor_preflight_verify import SpineMotorPreflightVerify
from skeleton.persistence.spine_runtime_selection import SpineRuntimeSelection
from skeleton.persistence.spine_runtime_selection_verify import SpineRuntimeSelectionVerify
from skeleton.persistence.spine_cutover_rehearsal import SpineCutoverRehearsal
from skeleton.persistence.spine_cutover_rehearsal_verify import SpineCutoverRehearsalVerify
from skeleton.persistence.spine_cutover_authorization import SpineCutoverAuthorization
from skeleton.persistence.spine_cutover_authorization_verify import SpineCutoverAuthorizationVerify
from skeleton.persistence.spine_cutover_effectiveness import SpineCutoverEffectiveness
from skeleton.persistence.spine_cutover_effectiveness_verify import SpineCutoverEffectivenessVerify
from skeleton.persistence.spine_selection_permit import SpineSelectionPermitLedger
from skeleton.persistence.spine_selection_permit_verify import SpineSelectionPermitVerify
from skeleton.persistence.spine_selection_consumption_verify import SpineSelectionConsumptionVerify
from skeleton.persistence.spine_driver_selection import SpineDriverSelectionLedger
from skeleton.persistence.spine_driver_selection_verify import SpineDriverSelectionVerify
from skeleton.persistence.spine_runtime_activation_gate import SpineRuntimeActivationGate
from skeleton.persistence.spine_runtime_activation_gate_verify import SpineRuntimeActivationGateVerify

_SNAPSHOT_EXPORTS = {
    "SnapshotStore",
    "restore_genesis_state",
    "restore_graph",
    "restore_mag",
    "restore_matrices",
    "restore_vector_store",
    "serialize_graph",
    "serialize_mag",
    "serialize_matrices",
    "serialize_vector_store",
    "snapshot_genesis_state",
}


def __getattr__(name: str) -> Any:
    if name not in _SNAPSHOT_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module("skeleton.persistence.snapshots")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | _SNAPSHOT_EXPORTS)


__all__ = [
    "ExecutionOutboxEvent",
    "ExecutionRepositoryConflict",
    "ExecutionRepositoryCorruption",
    "ExecutionRepositoryError",
    "SQLiteExecutionRepository",
    "ConversationAuthorizationError",
    "ConversationConflict",
    "ConversationNotFound",
    "ConversationRepositoryCorruption",
    "ConversationRepositoryError",
    "SQLiteConversationRepository",
    "MemoryConflict",
    "MemoryNotFound",
    "MemoryProjectionEvent",
    "MemoryRepositoryError",
    "MemoryRevision",
    "MongoMemoryRepository",
    "SQLiteMemoryRepository",
    "OperationOutboxEvent",
    "OperationStoreConflict",
    "OperationStoreCorruptionError",
    "OperationStoreError",
    "SQLiteOperationStore",
    "StoredOperation",
    "DurableOperationRuntime",
    "OutboxDispatchReport",
    "SQLiteInboxLedger",
    "SQLiteConsistencyFence",
    "SpineProjection",
    "SpineProjectionReport",
    "SpineLand",
    "SpineLandReport",
    "MongoInboxLedger",
    "MongoConsistencyFence",
    "SpineQuarantine",
    "SpineStatus",
    "MongoSpineProjection",
    "MongoProjectionReport",
    "SpineRepairPlan",
    "SpineLag",
    "SpineCatalog",
    "MongoCatalog",
    "SpineBatch",
    "SpineBatchReport",
    "SpineWitness",
    "SpineDrift",
    "SpineApplyGate",
    "SpineDigest",
    "SpineLedger",
    "SpineIndexPlan",
    "SpineBind",
    "SpineTracker",
    "SpinePair",
    "SpineReplay",
    "SpineSweep",
    "SpineExport",
    "SpineHold",
    "SpineManifest",
    "SpineMasterplan",
    "SpineReaccept",
    "SpineGate",
    "SpineWatch",
    "SpineCutover",
    "SpineWindow",
    "SpineSeal",
    "SpineGap",
    "SpinePoisonTicket",
    "SpinePoisonApply",
    "SpinePoisonWitness",
    "SpinePoisonChain",
    "SpineDispatchGuard",
    "SpineIndexBind",
    "SpineBindAudit",
    "SpineCutGate",
    "SpineSurface",
    "SpineProviderProbe",
    "SpinePrProbe",
    "SpineUnreadGap",
    "SpineSurfaceSeal",
    "SpineCiWitness",
    "SpineMergeGate",
    "SpineProbeReplay",
    "SpineMotorWitness",
    "SpineDispatchWitness",
    "SpineDark",
    "SpineEpochWitness",
    "SpineQuiet",
    "SpineQuietWitness",
    "SpineBindCard",
    "SpineBindJournal",
    "SpineBindRead",
    "SpineBindChain",
    "SpineBindTenant",
    "SpineBindReplay",
    "SpineBindSurface",
    "SpineBindGap",
    "SpineBindSnapshot",
    "SpineBindRecovery",
    "SpineBindCheckpoint",
    "SpineBindCheckpointReplay",
    "SpineBindCheckpointTenant",
    "SpineBindCheckpointChain",
    "SpineBindBundle",
    "SpineBindBundleVerify",
    "SpineBindRestoreReceipt",
    "SpineBindRestoreVerify",
    "SpineBindRestoreJournal",
    "SpineBindRestoreReplay",
    "SpineBindRestoreTenant",
    "SpineBindRestoreChain",
    "SpineBindRestoreContinuity",
    "SpineBindRestoreExport",
    "SpineBindRestoreExportVerify",
    "SpineMotorPlan",
    "SpineMotorBootstrap",
    "SpineMotorBootstrapVerify",
    "SpineMotorBootstrapReplay",
    "SpineMotorPreflight",
    "SpineMotorPreflightVerify",
    "SpineRuntimeSelection",
    "SpineRuntimeSelectionVerify",
    "SpineCutoverRehearsal",
    "SpineCutoverRehearsalVerify",
    "SpineCutoverAuthorization",
    "SpineCutoverAuthorizationVerify",
    "SpineCutoverEffectiveness",
    "SpineCutoverEffectivenessVerify",
    "SpineSelectionPermitLedger",
    "SpineSelectionPermitVerify",
    "SpineSelectionConsumptionVerify",
    "SpineDriverSelectionLedger",
    "SpineDriverSelectionVerify",
    "SpineRuntimeActivationGate",
    "SpineRuntimeActivationGateVerify",
    "SnapshotStore",
    "snapshot_genesis_state",
    "restore_genesis_state",
    "serialize_vector_store",
    "restore_vector_store",
    "serialize_mag",
    "restore_mag",
    "serialize_graph",
    "restore_graph",
    "serialize_matrices",
    "restore_matrices",
]
