"""Bounded recovery state for frontier execution."""

from dataclasses import dataclass


@dataclass
class RecoveryState:
    attempts: int = 0
    recovered: int = 0

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        for name, value in (("attempts", self.attempts), ("recovered", self.recovered)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.recovered > self.attempts:
            raise ValueError("recovered cannot exceed attempts")

    def record_attempt(self) -> int:
        self.attempts += 1
        return self.attempts

    def record_recovery(self) -> int:
        if self.recovered >= self.attempts:
            raise RuntimeError("cannot record recovery without an outstanding attempt")
        self.recovered += 1
        return self.recovered

    @property
    def recovery_rate(self) -> float:
        return 0.0 if self.attempts == 0 else self.recovered / self.attempts
