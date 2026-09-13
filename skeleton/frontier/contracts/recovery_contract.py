"""Recovery contract with bounded retry semantics."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RecoveryContract:
    request_id: str
    attempts: int
    recovered: bool
