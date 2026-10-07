"""Explicit deterministic decision records for auditable control flow."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Decision:
    action: str
    allowed: bool
    reason: str
    evidence: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("action must not be empty")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
