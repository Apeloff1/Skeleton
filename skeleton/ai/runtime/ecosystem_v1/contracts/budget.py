"""Conservative monotonic budgets, delegation and deadline checks."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import time

class AdmissionError(RuntimeError):
    """Request exceeds authorized resources or cannot run safely."""

@dataclass(frozen=True)
class Budget:
    tokens: int
    bytes: int
    steps: int
    deadline: float

    def __post_init__(self) -> None:
        for key in ("tokens", "bytes", "steps"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise AdmissionError("invalid " + key)
        if type(self.deadline) not in (float, int) or not math.isfinite(self.deadline) or self.deadline <= 0:
            raise AdmissionError("invalid deadline")

    @classmethod
    def for_seconds(cls, *, tokens: int, bytes: int, steps: int, seconds: float) -> "Budget":
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise AdmissionError("invalid duration")
        return cls(tokens, bytes, steps, time.monotonic() + seconds)

    def consume(self, *, tokens: int = 0, bytes: int = 0, steps: int = 0,
                now: float | None = None) -> "Budget":
        instant = time.monotonic() if now is None else now
        if type(instant) not in (int, float) or not math.isfinite(instant) or instant >= self.deadline:
            raise AdmissionError("operation deadline exceeded")
        changes = {"tokens": tokens, "bytes": bytes, "steps": steps}
        for key, count in changes.items():
            if type(count) is not int or count < 0 or count > getattr(self, key):
                raise AdmissionError(key + " budget exceeded")
        return replace(self, **{key: getattr(self, key) - value for key, value in changes.items()})

    def delegate(self, *, tokens: int, bytes: int, steps: int) -> tuple["Budget", "Budget"]:
        remaining = self.consume(tokens=tokens, bytes=bytes, steps=steps)
        child = Budget(tokens, bytes, steps, self.deadline)
        return remaining, child
