"""Versioned receipt migration with explicit semantic-preservation declarations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

from .execution_receipt import ExecutionReceipt

@dataclass(frozen=True, slots=True)
class MigrationInvariant:
    name: str
    required: bool = True

CORE_INVARIANTS: Final = (
    MigrationInvariant("semantic_request_identity"),
    MigrationInvariant("runtime_execution_identity"),
    MigrationInvariant("context_identity"),
    MigrationInvariant("admission_policy_identity"),
    MigrationInvariant("predecessor_continuity"),
)

@dataclass(frozen=True, slots=True)
class MigrationResult:
    source_digest: str
    target: ExecutionReceipt
    preserved: tuple[str,...]

    def __post_init__(self) -> None:
        names={item.name for item in CORE_INVARIANTS if item.required}
        if set(self.preserved)!=names:
            raise ValueError("migration must explicitly preserve all core invariants")
        if self.target.predecessor_digest!=self.source_digest:
            raise ValueError("migration target must bind source predecessor")

def migrate_receipt(source: ExecutionReceipt, *, algorithm: str) -> MigrationResult:
    target=source.reattest(algorithm=algorithm)
    preserved=tuple(item.name for item in CORE_INVARIANTS if item.required)
    return MigrationResult(source.digest,target,preserved)

def verify_migration(result: MigrationResult, source: ExecutionReceipt) -> bool:
    target=result.target
    return (
        result.source_digest==source.digest
        and target.predecessor_digest==source.digest
        and target.semantic_request_digest==source.semantic_request_digest
        and target.runtime_receipt_digest==source.runtime_receipt_digest
        and target.context_digest==source.context_digest
        and target.admission_policy_digest==source.admission_policy_digest
    )

__all__=["CORE_INVARIANTS","MigrationInvariant","MigrationResult","migrate_receipt","verify_migration"]
