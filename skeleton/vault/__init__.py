"""
Skeleton Vault Package

Exports:
- AccessPolicy: Role-based access control
- Role: Named role with permissions
- Permission: Permission enum
- EnvelopeKMS: Key envelope encryption
- Predefined roles: ROLE_GUEST, ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN
- AuditLog / WORM refuse-on-boot helpers (AuditChainBroken, verify_chain_or_refuse)
- ShamirSeal: secret sharing seal
"""

from skeleton.vault.access import (
    ROLE_ADMIN,
    ROLE_GUEST,
    ROLE_OPERATOR,
    ROLE_USER,
    AccessPolicy,
    EnvelopeKMS,
    Permission,
    Role,
)
from skeleton.vault.audit import (
    AuditChainBroken,
    AuditEntry,
    AuditError,
    AuditLog,
    verify_chain_or_refuse,
)
from skeleton.vault.shamir import ShamirSeal
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
    GovernedDataRecord,
    LifecycleConflict,
    LifecycleError,
    LifecycleState,
)
from skeleton.vault.data_governance import (
    DataClass,
    DataGovernanceDenied,
    DataGovernanceError,
    ProviderTransferDecision,
    ProviderTransferRequest,
    evaluate_provider_transfer,
    require_provider_transfer,
)
from skeleton.vault.governance_registry import (
    CanonicalDataPlane,
    CanonicalWritePolicy,
    GovernanceContext,
    GovernanceRegistry,
    RegisteredProviderTransferDecision,
)
from skeleton.vault.lifecycle_adapters import (
    DeletionExecutionResult,
    GovernedExport,
    LifecycleAdapterError,
    LifecycleAdapterMissing,
    LifecycleAdapterRegistry,
    LifecycleExecutionError,
    LifecycleExecutor,
    MemoryDeletionAdapter,
    MongoCollectionLifecycleAdapter,
    RetrievalIndexDeletionAdapter,
)

__all__ = [
    "AccessPolicy",
    "Role",
    "Permission",
    "EnvelopeKMS",
    "ROLE_GUEST",
    "ROLE_USER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
    "AuditChainBroken",
    "AuditEntry",
    "AuditError",
    "AuditLog",
    "verify_chain_or_refuse",
    "ShamirSeal",
    "DataClass",
    "DataGovernanceDenied",
    "DataGovernanceError",
    "ProviderTransferDecision",
    "ProviderTransferRequest",
    "evaluate_provider_transfer",
    "require_provider_transfer",
    "DataLifecycleRegistry",
    "DeletionAction",
    "DeletionPlan",
    "DeletionReceipt",
    "GovernedDataRecord",
    "LifecycleConflict",
    "LifecycleError",
    "LifecycleState",
    "CanonicalDataPlane",
    "CanonicalWritePolicy",
    "GovernanceContext",
    "GovernanceRegistry",
    "RegisteredProviderTransferDecision",
    "DeletionExecutionResult",
    "GovernedExport",
    "LifecycleAdapterError",
    "LifecycleAdapterMissing",
    "LifecycleAdapterRegistry",
    "LifecycleExecutionError",
    "LifecycleExecutor",
    "MemoryDeletionAdapter",
    "MongoCollectionLifecycleAdapter",
    "RetrievalIndexDeletionAdapter",
]
