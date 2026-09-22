"""Kernel assurance event primitives.

Small immutable-style records used to carry validation outcomes between
kernel admission, attestation, and downstream state consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Mapping, Any


class AssuranceState(str, Enum):
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssuranceEvent:
    """A bounded validation decision emitted by the kernel boundary."""

    task_id: str
    state: AssuranceState
    evidence_digest: str
    source: str = "kernel"
    created_at: float = field(default_factory=time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def valid(self) -> bool:
        return bool(self.task_id and self.evidence_digest)

    def card(self) -> dict[str, Any]:
        return {
            "kind": "assurance-event",
            "task_id": self.task_id,
            "state": self.state.value,
            "evidence_digest": self.evidence_digest,
            "source": self.source,
        }


def accepted(task_id: str, evidence_digest: str) -> AssuranceEvent:
    return AssuranceEvent(task_id, AssuranceState.ACCEPTED, evidence_digest)


def rejected(task_id: str, evidence_digest: str) -> AssuranceEvent:
    return AssuranceEvent(task_id, AssuranceState.REJECTED, evidence_digest)
