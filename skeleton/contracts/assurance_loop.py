"""Assurance loop integration primitives.

Connects evidence decisions with feedback routing without granting
execution authority to the assurance layer.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class FeedbackRoute(str, Enum):
    STABLE_MEMORY = "stable_memory"
    REVIEW_QUEUE = "review_queue"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssuranceDecision:
    task_id: str
    route: FeedbackRoute
    evidence_digest: str
    reason: str


def route_feedback(
    task_id: str,
    classification: str,
    evidence_digest: str,
) -> AssuranceDecision:
    """Route validated feedback into the appropriate state boundary."""
    if not task_id or not evidence_digest:
        return AssuranceDecision(
            task_id=task_id,
            route=FeedbackRoute.REJECTED,
            evidence_digest=evidence_digest,
            reason="missing_identity_or_evidence",
        )

    if classification == "STABLE":
        return AssuranceDecision(
            task_id=task_id,
            route=FeedbackRoute.STABLE_MEMORY,
            evidence_digest=evidence_digest,
            reason="validated_evidence",
        )

    if classification == "TEMPORARY":
        return AssuranceDecision(
            task_id=task_id,
            route=FeedbackRoute.REVIEW_QUEUE,
            evidence_digest=evidence_digest,
            reason="awaiting_validation",
        )

    return AssuranceDecision(
        task_id=task_id,
        route=FeedbackRoute.REJECTED,
        evidence_digest=evidence_digest,
        reason="invalid_or_rejected_evidence",
    )
