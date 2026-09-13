"""Bounded recovery state for frontier execution."""
from dataclasses import dataclass

@dataclass
class RecoveryState:
    attempts: int = 0
    recovered: int = 0

    def record_attempt(self) -> int:
        self.attempts += 1
        return self.attempts

    def record_recovery(self) -> int:
        self.recovered += 1
        return self.recovered

    @property
    def recovery_rate(self) -> float:
        return 0.0 if self.attempts == 0 else self.recovered / self.attempts
