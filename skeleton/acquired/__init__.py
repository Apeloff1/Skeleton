"""Skeleton acquired capabilities.

The acquired namespace is the quarantine/integration seam for reusable systems
mined from older Apeloff1 projects. Capabilities live here until they are
proven stable enough to move into a canonical Skeleton subsystem.
"""

from skeleton.acquired.audit_ledger import (
    AuditChainError,
    AuditEntry,
    GENESIS_HASH,
    TamperEvidentAuditLog,
)
from skeleton.acquired.ingest import (
    Asset,
    AssetIngestor,
    AssetLibrary,
    AssetValidator,
)
from skeleton.acquired.learning import (
    AdaptiveLearningEngine,
    DifficultyZone,
    LearningSignal,
    ProgressionTracker,
    Scaffold,
    ScaffoldType,
    ZPDResult,
)
from skeleton.acquired.runtime_guard import (
    AdaptiveGate,
    AdmissionVerdict,
    ChaosGovernor,
    DegradationRung,
    RuntimePolicy,
    WorkPriority,
)

__all__ = [
    "AdaptiveGate",
    "AdaptiveLearningEngine",
    "AdmissionVerdict",
    "Asset",
    "AssetIngestor",
    "AssetLibrary",
    "AssetValidator",
    "AuditChainError",
    "AuditEntry",
    "ChaosGovernor",
    "DegradationRung",
    "DifficultyZone",
    "GENESIS_HASH",
    "LearningSignal",
    "ProgressionTracker",
    "RuntimePolicy",
    "Scaffold",
    "ScaffoldType",
    "TamperEvidentAuditLog",
    "WorkPriority",
    "ZPDResult",
]
