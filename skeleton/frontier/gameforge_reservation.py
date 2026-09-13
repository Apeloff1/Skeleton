"""Explicit immutable reservation identity for bounded runtime resources."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Reservation:
    request_id: str
    sequence: int

    def __post_init__(self):
        if not self.request_id:
            raise ValueError("request_id is required")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("sequence must be non-negative")
