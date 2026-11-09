"""Governed claim registry with explicit promotion prerequisites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


_ALLOWED_TRANSITIONS = {
    "hypothesis": {"hypothesis", "supported", "rejected", "conflicted"},
    "supported": {"supported", "conflicted", "rejected"},
    "conflicted": {"conflicted", "supported", "rejected"},
    "rejected": {"rejected"},
}


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    proposition: str
    status: str = "hypothesis"
    quality_gate_digest: str | None = None
    quorum_digest: str | None = None
    replication_digest: str | None = None
    evidence_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.proposition:
            raise ReverseEngineeringError("claim record identity is required")
        if self.status not in _ALLOWED_TRANSITIONS:
            raise ReverseEngineeringError("invalid claim status")
        for digest in (
            self.quality_gate_digest,
            self.quorum_digest,
            self.replication_digest,
            *self.evidence_digests,
        ):
            if digest is not None and not is_sha256_digest(digest):
                raise ReverseEngineeringError("claim digests must be sha256 hex digests")
        if len(self.evidence_digests) != len(set(self.evidence_digests)):
            raise ReverseEngineeringError("claim evidence digests must be unique")


@dataclass(frozen=True)
class ClaimTransition:
    claim_id: str
    from_status: str
    to_status: str
    reason: str
    transition_digest: str


@dataclass(frozen=True)
class ClaimRegistry:
    records: tuple[ClaimRecord, ...] = ()
    transitions: tuple[ClaimTransition, ...] = ()

    def __post_init__(self) -> None:
        ids = [record.claim_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ReverseEngineeringError("claim registry ids must be unique")

    def get(self, claim_id: str) -> ClaimRecord:
        for record in self.records:
            if record.claim_id == claim_id:
                return record
        raise ReverseEngineeringError(f"unknown claim_id: {claim_id!r}")

    def add(self, record: ClaimRecord) -> "ClaimRegistry":
        if any(existing.claim_id == record.claim_id for existing in self.records):
            raise ReverseEngineeringError(f"duplicate claim_id: {record.claim_id!r}")
        return ClaimRegistry(
            records=tuple(sorted(self.records + (record,), key=lambda item: item.claim_id)),
            transitions=self.transitions,
        )

    def transition(
        self,
        claim_id: str,
        to_status: str,
        *,
        reason: str,
        quality_gate_passed: bool = False,
        quorum_met: bool = False,
        replication_passed: bool = False,
    ) -> "ClaimRegistry":
        if not reason:
            raise ReverseEngineeringError("claim transition requires reason")
        current = self.get(claim_id)
        if to_status not in _ALLOWED_TRANSITIONS[current.status]:
            raise ReverseEngineeringError(
                f"invalid claim transition: {current.status!r} -> {to_status!r}"
            )
        if to_status == "supported" and not (
            quality_gate_passed and quorum_met and replication_passed
        ):
            raise ReverseEngineeringError(
                "supported transition requires quality gate, quorum, and replication"
            )

        updated = ClaimRecord(
            claim_id=current.claim_id,
            proposition=current.proposition,
            status=to_status,
            quality_gate_digest=current.quality_gate_digest,
            quorum_digest=current.quorum_digest,
            replication_digest=current.replication_digest,
            evidence_digests=current.evidence_digests,
        )
        records = tuple(
            updated if record.claim_id == claim_id else record
            for record in self.records
        )
        transition_payload = {
            "claim_id": claim_id,
            "from_status": current.status,
            "to_status": to_status,
            "reason": reason,
            "ordinal": len(self.transitions),
        }
        transition = ClaimTransition(
            claim_id=claim_id,
            from_status=current.status,
            to_status=to_status,
            reason=reason,
            transition_digest=stable_digest(transition_payload),
        )
        return ClaimRegistry(records=records, transitions=self.transitions + (transition,))

    @property
    def digest(self) -> str:
        return stable_digest(
            {
                "records": [
                    {
                        "claim_id": record.claim_id,
                        "proposition": record.proposition,
                        "status": record.status,
                        "quality_gate_digest": record.quality_gate_digest,
                        "quorum_digest": record.quorum_digest,
                        "replication_digest": record.replication_digest,
                        "evidence_digests": list(record.evidence_digests),
                    }
                    for record in sorted(self.records, key=lambda item: item.claim_id)
                ],
                "transitions": [
                    {
                        "claim_id": transition.claim_id,
                        "from_status": transition.from_status,
                        "to_status": transition.to_status,
                        "reason": transition.reason,
                        "transition_digest": transition.transition_digest,
                    }
                    for transition in self.transitions
                ],
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "records": [
                {
                    "claim_id": record.claim_id,
                    "proposition": record.proposition,
                    "status": record.status,
                    "quality_gate_digest": record.quality_gate_digest,
                    "quorum_digest": record.quorum_digest,
                    "replication_digest": record.replication_digest,
                    "evidence_digests": list(record.evidence_digests),
                }
                for record in sorted(self.records, key=lambda item: item.claim_id)
            ],
            "transitions": [
                {
                    "claim_id": transition.claim_id,
                    "from_status": transition.from_status,
                    "to_status": transition.to_status,
                    "reason": transition.reason,
                    "transition_digest": transition.transition_digest,
                }
                for transition in self.transitions
            ],
            "digest": self.digest,
        }
