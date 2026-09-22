"""Assurance feedback routing primitives.

Connects validated execution outcomes to Jeeves feedback consumers.
The module intentionally stores only validated metadata and evidence references.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class FeedbackState(str, Enum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssuranceFeedback:
    task_id: str
    state: FeedbackState
    evidence_ids: Tuple[str, ...]
    summary: str


def build_feedback(task_id: str, classification: str, evidence_ids: Tuple[str, ...], summary: str) -> AssuranceFeedback:
    if not task_id:
        raise ValueError("task identity required")
    if not evidence_ids:
        return AssuranceFeedback(task_id, FeedbackState.NEEDS_REVIEW, (), summary)

    if classification == "STABLE":
        return AssuranceFeedback(task_id, FeedbackState.ACCEPTED, evidence_ids, summary)
    if classification == "REJECTED":
        return AssuranceFeedback(task_id, FeedbackState.REJECTED, evidence_ids, summary)

    return AssuranceFeedback(task_id, FeedbackState.NEEDS_REVIEW, evidence_ids, summary)
