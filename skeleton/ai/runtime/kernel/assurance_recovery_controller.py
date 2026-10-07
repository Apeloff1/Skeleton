"""Assurance recovery boundary.

Keeps recovery decisions separate from execution and preserves bounded state
transitions after assurance failures.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RecoveryAction(str, Enum):
    RETRY_VALIDATION = "retry_validation"
    REQUIRE_REVIEW = "require_review"
    HALT = "halt"


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    task_id: Optional[str] = None


RECOVERABLE = {
    "VALIDATION_FAILED": RecoveryAction.RETRY_VALIDATION,
    "EVIDENCE_MISSING": RecoveryAction.REQUIRE_REVIEW,
    "IDENTITY_MISSING": RecoveryAction.HALT,
    "DIGEST_MISMATCH": RecoveryAction.HALT,
    "REPLAY_DETECTED": RecoveryAction.HALT,
    "INVALID_TRANSITION": RecoveryAction.REQUIRE_REVIEW,
}


def decide_recovery(error_code: str, task_id: Optional[str] = None) -> RecoveryDecision:
    action = RECOVERABLE.get(error_code, RecoveryAction.REQUIRE_REVIEW)
    return RecoveryDecision(action=action, reason=error_code, task_id=task_id)
