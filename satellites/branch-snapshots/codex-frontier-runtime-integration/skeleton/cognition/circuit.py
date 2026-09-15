"""Failure containment primitives for autonomous execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    half_open: bool = False
    history: list[str] = field(default_factory=list)

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if monotonic() - self.opened_at >= self.recovery_timeout:
            self.half_open = True
            return False
        return True

    def allow(self) -> bool:
        return not self.open

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.half_open = False
        self.history.append("success")

    def record_failure(self, reason: str = "failure") -> None:
        self.failures += 1
        self.history.append(reason)
        if self.failures >= self.failure_threshold or self.half_open:
            self.opened_at = monotonic()
            self.half_open = False

    def snapshot(self) -> dict[str, object]:
        return {"failure_threshold": self.failure_threshold, "recovery_timeout": self.recovery_timeout, "failures": self.failures, "opened": self.open, "history": list(self.history)}
