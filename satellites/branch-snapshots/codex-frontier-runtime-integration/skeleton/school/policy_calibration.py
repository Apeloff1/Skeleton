"""Deterministic empirical calibration for Jeeves policy reliability."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class PolicyStats:
    attempts: int = 0
    successes: int = 0
    reward: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def sample_weight(self) -> float:
        """Shrink sparse observations toward an uninformative 0.5 prior."""
        return self.attempts / (self.attempts + 4.0)


@dataclass
class PolicyCalibrator:
    stats: dict[str, PolicyStats] = field(default_factory=dict)
    learning_rate: float = 0.2

    def __post_init__(self) -> None:
        if not 0 < self.learning_rate <= 1:
            raise ValueError("learning_rate must be in (0, 1]")

    def observe(self, action: str, *, reward: float, successful: bool) -> PolicyStats:
        reward = max(-1.0, min(1.0, reward))
        stats = self.stats.setdefault(action, PolicyStats())
        stats.attempts += 1
        stats.successes += int(successful)
        stats.reward = stats.reward * (1 - self.learning_rate) + reward * self.learning_rate
        return stats

    def reliability(self, action: str) -> float:
        stats = self.stats.get(action)
        if not stats or not stats.attempts:
            return 0.5
        raw = 0.6 * stats.success_rate + 0.4 * ((stats.reward + 1.0) / 2.0)
        return max(0.0, min(1.0, 0.5 + stats.sample_weight * (raw - 0.5)))

    def ranking(self) -> tuple[tuple[str, float], ...]:
        return tuple(
            sorted(
                ((action, self.reliability(action)) for action in self.stats),
                key=lambda item: (-item[1], item[0]),
            )
        )

    def snapshot(self) -> Mapping[str, float]:
        return {action: self.reliability(action) for action in sorted(self.stats)}
