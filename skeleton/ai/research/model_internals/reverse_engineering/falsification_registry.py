"""Explicit falsifier registry for reverse-engineering claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class Falsifier:
    falsifier_id: str
    claim_id: str
    description_digest: str
    evidence_digest: str | None = None
    triggered: bool = False

    def __post_init__(self) -> None:
        if not self.falsifier_id or not self.claim_id:
            raise ReverseEngineeringError("falsifier identity is required")
        if not is_sha256_digest(self.description_digest):
            raise ReverseEngineeringError("description_digest must be sha256 hex")
        if self.evidence_digest is not None and not is_sha256_digest(self.evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be sha256 hex when present")
        if self.triggered and self.evidence_digest is None:
            raise ReverseEngineeringError("triggered falsifier requires evidence_digest")


@dataclass(frozen=True)
class FalsificationReport:
    claim_id: str
    falsifier_count: int
    evaluated_count: int
    triggered_count: int
    unevaluated_count: int
    status: str
    triggered_ids: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "falsifier_count": self.falsifier_count,
            "evaluated_count": self.evaluated_count,
            "triggered_count": self.triggered_count,
            "unevaluated_count": self.unevaluated_count,
            "status": self.status,
            "triggered_ids": list(self.triggered_ids),
            "digest": self.digest,
        }


def evaluate_falsifiers(
    falsifiers: Sequence[Falsifier],
) -> tuple[FalsificationReport, ...]:
    if not falsifiers:
        raise ReverseEngineeringError("falsification registry requires falsifiers")
    ids = [item.falsifier_id for item in falsifiers]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("falsifier ids must be unique")
    grouped: dict[str, list[Falsifier]] = {}
    for item in falsifiers:
        grouped.setdefault(item.claim_id, []).append(item)

    reports: list[FalsificationReport] = []
    for claim_id, items in sorted(grouped.items()):
        evaluated = [item for item in items if item.evidence_digest is not None]
        triggered = [item for item in evaluated if item.triggered]
        status = "falsified" if triggered else ("survived" if len(evaluated) == len(items) else "incomplete")
        payload = {
            "claim_id": claim_id,
            "falsifiers": [
                {
                    "falsifier_id": item.falsifier_id,
                    "description_digest": item.description_digest,
                    "evidence_digest": item.evidence_digest,
                    "triggered": item.triggered,
                }
                for item in sorted(items, key=lambda value: value.falsifier_id)
            ],
        }
        reports.append(
            FalsificationReport(
                claim_id=claim_id,
                falsifier_count=len(items),
                evaluated_count=len(evaluated),
                triggered_count=len(triggered),
                unevaluated_count=len(items) - len(evaluated),
                status=status,
                triggered_ids=tuple(sorted(item.falsifier_id for item in triggered)),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
