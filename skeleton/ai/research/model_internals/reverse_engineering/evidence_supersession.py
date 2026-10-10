"""Evidence supersession graph for replacing stale or invalidated reports safely."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EvidenceRevision:
    evidence_id: str
    evidence_digest: str
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ReverseEngineeringError("evidence revision requires identity")
        if not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be sha256 hex")
        if self.supersedes_id == self.evidence_id:
            raise ReverseEngineeringError("evidence revision cannot supersede itself")


@dataclass(frozen=True)
class EvidenceSupersessionReport:
    revision_count: int
    root_count: int
    active_tip_count: int
    active_tip_ids: tuple[str, ...]
    missing_predecessor_count: int
    cycle_free: bool
    valid: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "revision_count": self.revision_count,
            "root_count": self.root_count,
            "active_tip_count": self.active_tip_count,
            "active_tip_ids": list(self.active_tip_ids),
            "missing_predecessor_count": self.missing_predecessor_count,
            "cycle_free": self.cycle_free,
            "valid": self.valid,
            "digest": self.digest,
        }


def analyze_evidence_supersession(
    revisions: Sequence[EvidenceRevision],
) -> EvidenceSupersessionReport:
    if not revisions:
        raise ReverseEngineeringError("evidence supersession requires revisions")
    ids = [item.evidence_id for item in revisions]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("evidence revision ids must be unique")
    by_id = {item.evidence_id: item for item in revisions}
    superseded: set[str] = set()
    missing = 0
    for item in revisions:
        if item.supersedes_id is None:
            continue
        if item.supersedes_id not in by_id:
            missing += 1
        else:
            superseded.add(item.supersedes_id)

    state: dict[str, int] = {}
    cycle = False

    def visit(evidence_id: str) -> None:
        nonlocal cycle
        marker = state.get(evidence_id, 0)
        if marker == 1:
            cycle = True
            return
        if marker == 2:
            return
        state[evidence_id] = 1
        predecessor = by_id[evidence_id].supersedes_id
        if predecessor in by_id:
            visit(predecessor)
        state[evidence_id] = 2

    for evidence_id in sorted(by_id):
        visit(evidence_id)

    tips = tuple(sorted(set(by_id) - superseded))
    payload = {
        "revisions": [
            {
                "evidence_id": item.evidence_id,
                "evidence_digest": item.evidence_digest,
                "supersedes_id": item.supersedes_id,
            }
            for item in sorted(revisions, key=lambda value: value.evidence_id)
        ]
    }
    valid = missing == 0 and not cycle
    return EvidenceSupersessionReport(
        revision_count=len(revisions),
        root_count=sum(item.supersedes_id is None for item in revisions),
        active_tip_count=len(tips),
        active_tip_ids=tips,
        missing_predecessor_count=missing,
        cycle_free=not cycle,
        valid=valid,
        digest=stable_digest(payload),
    )
