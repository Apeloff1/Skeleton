"""Evidence-bound governance for canonical memory reconciliation.

Resolution is deliberately separated from mutation. A deterministic receipt
must be issued before a caller may promote/supersede canonical memories.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from skeleton.memory.reconciliation import (
    MemoryAction,
    MemoryConflictResolver,
    MemoryConflictResolution,
    MemoryConflictSet,
)


class ReconciliationGovernanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReconciliationReceipt:
    conflict_id: str
    resolution: str
    winner_id: str | None
    superseded_ids: tuple[str, ...]
    policy_digest: str
    evidence_refs: tuple[str, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        if not self.evidence_refs:
            raise ReconciliationGovernanceError("reconciliation receipt requires evidence")
        if tuple(sorted(set(self.evidence_refs))) != self.evidence_refs:
            raise ReconciliationGovernanceError("evidence refs must be unique and sorted")
        if len(self.policy_digest) != 64 or len(self.receipt_digest) != 64:
            raise ReconciliationGovernanceError("receipt digests must be sha256")


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def issue_reconciliation_receipt(
    conflict: MemoryConflictSet,
    *,
    resolver: MemoryConflictResolver,
    quality_actions: Mapping[str, MemoryAction],
    evidence_refs: tuple[str, ...],
) -> tuple[MemoryConflictSet, ReconciliationReceipt]:
    refs = tuple(sorted(set(str(ref).strip() for ref in evidence_refs if str(ref).strip())))
    if not refs:
        raise ReconciliationGovernanceError("resolution requires evidence")
    resolved = resolver.resolve(conflict, quality_actions=quality_actions)
    if resolved.resolution is MemoryConflictResolution.UNRESOLVED:
        raise ReconciliationGovernanceError("ambiguous conflict cannot be promoted")
    policy = resolver.policy
    policy_payload = {
        "min_confidence_margin": policy.min_confidence_margin,
        "min_provenance_margin": policy.min_provenance_margin,
        "require_winner_provenance": policy.require_winner_provenance,
    }
    policy_digest = _sha(policy_payload)
    body = {
        "conflict": resolved.to_dict(),
        "quality_actions": {key: MemoryAction(value).value for key, value in sorted(quality_actions.items())},
        "policy_digest": policy_digest,
        "evidence_refs": refs,
    }
    digest = _sha(body)
    return resolved, ReconciliationReceipt(
        conflict_id=resolved.conflict_id,
        resolution=resolved.resolution.value,
        winner_id=resolved.winner_id,
        superseded_ids=resolved.superseded_ids,
        policy_digest=policy_digest,
        evidence_refs=refs,
        receipt_digest=digest,
    )


def authorize_supersession(conflict: MemoryConflictSet, receipt: ReconciliationReceipt) -> tuple[str, tuple[str, ...]]:
    if conflict.resolution is not MemoryConflictResolution.SUPERSEDE:
        raise ReconciliationGovernanceError("only supersede resolutions authorize mutation")
    if receipt.conflict_id != conflict.conflict_id or receipt.resolution != conflict.resolution.value:
        raise ReconciliationGovernanceError("receipt does not bind conflict resolution")
    if receipt.winner_id != conflict.winner_id or receipt.superseded_ids != conflict.superseded_ids:
        raise ReconciliationGovernanceError("receipt does not bind supersession set")
    assert conflict.winner_id is not None
    return conflict.winner_id, conflict.superseded_ids
