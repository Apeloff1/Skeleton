"""Independent replication ledger for reverse-engineering claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import InferenceClaim, ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ReplicationAttempt:
    attempt_id: str
    claim_id: str
    protocol_digest: str
    evidence_digest: str
    independent_actor: str
    reproduced: bool

    def __post_init__(self) -> None:
        if not self.attempt_id or not self.claim_id or not self.independent_actor:
            raise ReverseEngineeringError("replication attempt identity fields are required")
        if len(self.protocol_digest) != 64 or len(self.evidence_digest) != 64:
            raise ReverseEngineeringError("replication digests must be sha256 length")


@dataclass(frozen=True)
class ReplicationStatus:
    claim_id: str
    attempts: int
    independent_actors: int
    reproductions: int
    reproduction_ratio: float
    independently_replicated: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "attempts": self.attempts,
            "independent_actors": self.independent_actors,
            "reproductions": self.reproductions,
            "reproduction_ratio": self.reproduction_ratio,
            "independently_replicated": self.independently_replicated,
            "digest": self.digest,
        }


def replication_status(
    claim: InferenceClaim,
    attempts: Sequence[ReplicationAttempt],
    *,
    minimum_independent_actors: int = 2,
    minimum_ratio: float = 0.75,
) -> ReplicationStatus:
    relevant = [attempt for attempt in attempts if attempt.claim_id == claim.claim_id]
    actors = {attempt.independent_actor for attempt in relevant}
    reproductions = sum(1 for attempt in relevant if attempt.reproduced)
    ratio = round(reproductions / len(relevant), 12) if relevant else 0.0
    replicated = (
        claim.status == "supported"
        and len(actors) >= minimum_independent_actors
        and ratio >= minimum_ratio
    )
    payload = {
        "claim_id": claim.claim_id,
        "claim_status": claim.status,
        "attempts": [
            {
                "attempt_id": item.attempt_id,
                "protocol_digest": item.protocol_digest,
                "evidence_digest": item.evidence_digest,
                "independent_actor": item.independent_actor,
                "reproduced": item.reproduced,
            }
            for item in sorted(relevant, key=lambda value: value.attempt_id)
        ],
        "minimum_independent_actors": minimum_independent_actors,
        "minimum_ratio": minimum_ratio,
    }
    return ReplicationStatus(
        claim_id=claim.claim_id,
        attempts=len(relevant),
        independent_actors=len(actors),
        reproductions=reproductions,
        reproduction_ratio=ratio,
        independently_replicated=replicated,
        digest=stable_digest(payload),
    )
