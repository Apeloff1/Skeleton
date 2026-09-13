"""Normalized outcome values for frontier execution."""
from dataclasses import dataclass
from enum import Enum

class OutcomeKind(str, Enum):
    ACCEPTED = "accepted"
    SHED = "shed"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    request_id: str | None = None
    detail: str = ""
