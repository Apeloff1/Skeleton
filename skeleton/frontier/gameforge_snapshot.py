"""Small immutable runtime state snapshot for bounded observability."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RuntimeSnapshot:
    lifecycle: str
    dependencies_ready: bool
    active: int
    budget_used: int
    budget_capacity: int
    quota_used: int = 0
    queue_depth: int = 0
    health: float = 1.0

    def __post_init__(self):
        if not isinstance(self.lifecycle, str) or not self.lifecycle:
            raise TypeError("lifecycle must be a non-empty string")
        if not isinstance(self.dependencies_ready, bool):
            raise TypeError("dependencies_ready must be a boolean")
        counters = (self.active, self.budget_used, self.budget_capacity,
                    self.quota_used, self.queue_depth)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in counters):
            raise TypeError("runtime counters must be integers")
        if self.active < 0 or self.budget_used < 0 or self.budget_capacity <= 0:
            raise ValueError("runtime counters must be non-negative")
        if self.budget_used > self.budget_capacity:
            raise ValueError("budget_used exceeds budget_capacity")
        if self.quota_used < 0 or self.queue_depth < 0:
            raise ValueError("queue counters must be non-negative")
        if not isinstance(self.health, (int, float)) or isinstance(self.health, bool):
            raise TypeError("health must be numeric")
        if not isfinite(float(self.health)) or not 0.0 <= self.health <= 1.0:
            raise ValueError("health must be finite and between zero and one")

    @property
    def saturated(self):
        return self.active >= self.budget_capacity or self.budget_used >= self.budget_capacity

    @property
    def recoverable(self):
        return self.lifecycle not in {"stopped"} and self.dependencies_ready
