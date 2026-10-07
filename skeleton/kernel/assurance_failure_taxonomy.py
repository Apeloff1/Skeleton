"""Bounded assurance failure taxonomy.

Keeps failure classification separate from execution state.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class FailureKind(str, Enum):
    IDENTITY_MISSING = "identity_missing"
    EVIDENCE_MISSING = "evidence_missing"
    DIGEST_MISMATCH = "digest_mismatch"
    REPLAY_DETECTED = "replay_detected"
    INVALID_TRANSITION = "invalid_transition"
    VALIDATION_FAILED = "validation_failed"


@dataclass(frozen=True)
class AssuranceFailure:
    kind: FailureKind
    message: str
    task_id: Optional[str] = None
    evidence_digest: Optional[str] = None


def identity_failure(task_id=None):
    return AssuranceFailure(
        kind=FailureKind.IDENTITY_MISSING,
        message="task identity required",
        task_id=task_id,
    )


def evidence_failure(digest=None):
    return AssuranceFailure(
        kind=FailureKind.EVIDENCE_MISSING,
        message="evidence digest required",
        evidence_digest=digest,
    )
