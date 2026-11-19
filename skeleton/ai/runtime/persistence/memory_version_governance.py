"""Governed immutable memory revision export and rollback controls.

This layer intentionally wraps canonical repository history rather than
rewriting it. Rollback creates a new revision through the normal optimistic
write path and therefore preserves tombstones, provenance and projection
semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from skeleton.contracts.memory_record import MemoryState, MemoryWriteProposal
from skeleton.persistence.memory_repository import (
    MemoryConflict,
    MemoryNotFound,
    MemoryRevision,
    SQLiteMemoryRepository,
)


class MemoryVersionGovernanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryHistoryExport:
    memory_id: str
    tenant_id: str
    namespace: str
    head_version: int
    revision_digests: tuple[str, ...]
    history_digest: str

    def __post_init__(self) -> None:
        if self.head_version < 1 or len(self.revision_digests) != self.head_version:
            raise MemoryVersionGovernanceError("history must be contiguous through head")
        if any(len(d) != 64 for d in self.revision_digests):
            raise MemoryVersionGovernanceError("revision digest must be sha256")


def _revision_digest(revision: MemoryRevision) -> str:
    payload = {
        "memory_id": revision.memory_id,
        "tenant_id": revision.tenant_id,
        "namespace": revision.namespace,
        "version": revision.version,
        "predecessor_version": revision.predecessor_version,
        "mutation": revision.mutation,
        "committed_at": revision.committed_at.isoformat(),
        "record": revision.record.as_dict(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def export_history(repository: SQLiteMemoryRepository, memory_id: str, *, tenant_id: str, namespace: str) -> MemoryHistoryExport:
    revisions = repository.history(memory_id, tenant_id=tenant_id, namespace=namespace)
    if not revisions:
        raise MemoryNotFound("memory history not found in authority scope")
    versions = tuple(r.version for r in revisions)
    if versions != tuple(range(1, len(revisions) + 1)):
        raise MemoryVersionGovernanceError("memory history is not contiguous")
    digests = tuple(_revision_digest(r) for r in revisions)
    root = hashlib.sha256(json.dumps({"memory_id": memory_id, "digests": digests}, separators=(",", ":")).encode()).hexdigest()
    return MemoryHistoryExport(memory_id, tenant_id, namespace, revisions[-1].version, digests, root)


def governed_rollback(
    repository: SQLiteMemoryRepository,
    memory_id: str,
    *,
    tenant_id: str,
    namespace: str,
    target_version: int,
    expected_head_version: int,
    evidence_ref: str,
    operation_id: str,
    now: datetime | None = None,
):
    if target_version < 1:
        raise MemoryVersionGovernanceError("target_version must be positive")
    if not evidence_ref.strip() or not operation_id.strip():
        raise MemoryVersionGovernanceError("rollback requires evidence and operation identity")
    current = repository.get(memory_id, tenant_id=tenant_id, namespace=namespace, include_tombstoned=True)
    if current.version != expected_head_version:
        raise MemoryConflict("rollback expected head version mismatch")
    if current.state is MemoryState.TOMBSTONED:
        raise MemoryConflict("rollback cannot resurrect tombstoned memory")
    revisions = repository.history(memory_id, tenant_id=tenant_id, namespace=namespace)
    target = next((r.record for r in revisions if r.version == target_version), None)
    if target is None:
        raise MemoryNotFound("rollback target revision not found")
    if target.state is MemoryState.TOMBSTONED:
        raise MemoryConflict("rollback target is tombstoned")
    provenance = tuple(dict.fromkeys((*target.provenance_refs, evidence_ref, f"rollback-from:{current.version}", f"rollback-target:{target_version}")))
    proposal = MemoryWriteProposal(
        tenant_id=tenant_id,
        namespace=namespace,
        subject_id=current.subject_id,
        kind=target.kind,
        idempotency_key=f"rollback:{operation_id}",
        content=target.content,
        content_ref=target.content_ref,
        provenance_refs=provenance,
        source_operation_id=operation_id,
        target_memory_id=memory_id,
        expected_version=expected_head_version,
        expires_at=target.expires_at,
        data_class=target.data_class,
    )
    return repository.write(proposal, now=now)
