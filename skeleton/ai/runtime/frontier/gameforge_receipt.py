"""Immutable execution receipt for observable admission outcomes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    request_id: str
    decision: str
    reason: str

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.decision, str) or not self.decision:
            raise ValueError("decision must be a non-empty string")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be str")

    @property
    def accepted(self):
        return self.decision == "accept"

    @property
    def rejected(self):
        return not self.accepted
