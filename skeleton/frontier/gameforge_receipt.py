"""Immutable execution receipt for observable admission outcomes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    request_id: str
    decision: str
    reason: str

    def __post_init__(self):
        if not self.request_id:
            raise ValueError("request_id is required")
        if not self.decision:
            raise ValueError("decision is required")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be str")

    @property
    def accepted(self):
        return self.decision == "accept"

    @property
    def rejected(self):
        return not self.accepted
