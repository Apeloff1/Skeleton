"""Assurance transition validator.

Keeps assurance state changes explicit and bounded before downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TransitionError(ValueError):
    pass


class Transition(Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


_ALLOWED = {
    Transition.NEW: {Transition.ACCEPTED, Transition.REVIEW, Transition.REJECTED},
    Transition.REVIEW: {Transition.ACCEPTED, Transition.REJECTED},
    Transition.ACCEPTED: set(),
    Transition.REJECTED: set(),
}


@dataclass(frozen=True)
class TransitionRecord:
    task_id: str
    previous: Transition
    next: Transition
    evidence_digest: str


def validate_transition(
    *,
    task_id: str,
    previous: Transition,
    next_state: Transition,
    evidence_digest: Optional[str],
) -> TransitionRecord:
    if not task_id:
        raise TransitionError("task identity required")
    if not evidence_digest:
        raise TransitionError("evidence digest required")
    if next_state not in _ALLOWED.get(previous, set()):
        raise TransitionError(f"invalid transition {previous.value}->{next_state.value}")
    return TransitionRecord(
        task_id=task_id,
        previous=previous,
        next=next_state,
        evidence_digest=evidence_digest,
    )
