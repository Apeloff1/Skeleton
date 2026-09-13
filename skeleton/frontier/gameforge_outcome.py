"""Normalized, validated outcome values for frontier execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OutcomeKind(str, Enum):
    ACCEPTED = "accepted"
    SHED = "shed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Outcome:
    """Immutable execution outcome with explicit request provenance."""

    kind: OutcomeKind
    request_id: str | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OutcomeKind):
            raise TypeError("kind must be an OutcomeKind")
        if self.request_id is not None and (
            not isinstance(self.request_id, str) or not self.request_id.strip()
        ):
            raise ValueError("request_id must be None or a non-empty string")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")

    @property
    def terminal(self) -> bool:
        return self.kind in (OutcomeKind.COMPLETED, OutcomeKind.FAILED)

    @property
    def accepted(self) -> bool:
        return self.kind in (OutcomeKind.ACCEPTED, OutcomeKind.COMPLETED)

    @property
    def failed(self) -> bool:
        return self.kind is OutcomeKind.FAILED
