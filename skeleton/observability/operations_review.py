"""Cross-volume operations evidence review for VOL-180..VOL-187.

This module binds SLO, error-budget, cardinality, trace, profile, latency, cost,
and efficiency evidence into one immutable review receipt. It is deliberately
non-authoritative: it cannot release, route, scale, spend, or promote anything.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping


class OperationsReviewError(ValueError):
    """An operations evidence bundle is incomplete or internally inconsistent."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
        raise OperationsReviewError(f"{name} must be non-empty normalized text")
    return value


def _sha(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise OperationsReviewError(f"{name} must be a lowercase sha256 digest")
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise OperationsReviewError("operations review must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OperationsEvidence:
    review_id: str
    subject_id: str
    source_revision: str
    slo_assessment_digest: str
    budget_decision_digest: str
    cardinality_decision_digest: str
    trace_evidence_digest: str
    profile_finding_digest: str
    latency_assessment_digest: str
    cost_decision_digest: str
    efficiency_claim_digest: str
    status_inputs: Mapping[str, bool]
    blockers: tuple[str, ...]
    status: str
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_id", _token("review_id", self.review_id))
        object.__setattr__(self, "subject_id", _token("subject_id", self.subject_id))
        revision = str(self.source_revision).strip().lower()
        if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
            raise OperationsReviewError("source_revision must be a 40-character lowercase Git SHA")
        object.__setattr__(self, "source_revision", revision)

        for name in (
            "slo_assessment_digest",
            "budget_decision_digest",
            "cardinality_decision_digest",
            "trace_evidence_digest",
            "profile_finding_digest",
            "latency_assessment_digest",
            "cost_decision_digest",
            "efficiency_claim_digest",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))

        required = {
            "slo_target_met",
            "budget_healthy",
            "cardinality_accepted",
            "profile_not_regressed",
            "latency_within_budget",
            "cost_admitted",
            "efficiency_claim_valid",
        }
        supplied = dict(self.status_inputs)
        if set(supplied) != required or any(not isinstance(value, bool) for value in supplied.values()):
            raise OperationsReviewError("status_inputs must contain the exact boolean operations status set")
        object.__setattr__(self, "status_inputs", dict(sorted(supplied.items())))

        expected_blockers = tuple(sorted(
            key for key, value in supplied.items() if not value
        ))
        blockers = tuple(sorted(set(self.blockers)))
        if blockers != expected_blockers:
            raise OperationsReviewError("blockers must exactly match failed status inputs")
        object.__setattr__(self, "blockers", blockers)

        expected_status = "healthy" if not blockers else "attention_required"
        if self.status != expected_status:
            raise OperationsReviewError("status must match blocker evidence")
        if self.promotion_authority is not False:
            raise OperationsReviewError("operations review cannot grant promotion authority")

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "subject_id": self.subject_id,
            "source_revision": self.source_revision,
            "slo_assessment_digest": self.slo_assessment_digest,
            "budget_decision_digest": self.budget_decision_digest,
            "cardinality_decision_digest": self.cardinality_decision_digest,
            "trace_evidence_digest": self.trace_evidence_digest,
            "profile_finding_digest": self.profile_finding_digest,
            "latency_assessment_digest": self.latency_assessment_digest,
            "cost_decision_digest": self.cost_decision_digest,
            "efficiency_claim_digest": self.efficiency_claim_digest,
            "status_inputs": dict(self.status_inputs),
            "blockers": list(self.blockers),
            "status": self.status,
            "promotion_authority": False,
        }


def build_operations_review(
    *,
    review_id: str,
    subject_id: str,
    source_revision: str,
    evidence_digests: Mapping[str, str],
    status_inputs: Mapping[str, bool],
) -> OperationsEvidence:
    expected_evidence = {
        "slo_assessment_digest",
        "budget_decision_digest",
        "cardinality_decision_digest",
        "trace_evidence_digest",
        "profile_finding_digest",
        "latency_assessment_digest",
        "cost_decision_digest",
        "efficiency_claim_digest",
    }
    evidence = dict(evidence_digests)
    if set(evidence) != expected_evidence:
        raise OperationsReviewError("evidence_digests must contain the exact operations evidence set")
    failed = tuple(sorted(key for key, value in status_inputs.items() if value is False))
    return OperationsEvidence(
        review_id=review_id,
        subject_id=subject_id,
        source_revision=source_revision,
        status_inputs=status_inputs,
        blockers=failed,
        status="healthy" if not failed else "attention_required",
        **evidence,
    )


__all__ = [
    "OperationsEvidence",
    "OperationsReviewError",
    "build_operations_review",
]
