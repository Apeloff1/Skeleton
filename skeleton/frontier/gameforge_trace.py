"""Minimal deterministic trace records for frontier decisions."""
from dataclasses import dataclass

@dataclass(frozen=True)
class TraceRecord:
    request_id: str
    decision: str
    timestamp: int

    def key(self) -> tuple[str, int]:
        return (self.request_id, self.timestamp)
