"""Small immutable runtime state snapshot for bounded observability."""
from dataclasses import dataclass

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
        if self.active < 0 or self.budget_used < 0 or self.budget_capacity <= 0:
            raise ValueError("runtime counters must be non-negative")
        if self.budget_used > self.budget_capacity:
            raise ValueError("budget_used exceeds budget_capacity")
        if self.quota_used < 0 or self.queue_depth < 0:
            raise ValueError("queue counters must be non-negative")
        if not 0.0 <= self.health <= 1.0:
            raise ValueError("health must be between zero and one")

    @property
    def saturated(self):
        return self.active >= self.budget_capacity or self.budget_used >= self.budget_capacity

    @property
    def recoverable(self):
        return self.lifecycle not in {"stopped"} and self.dependencies_ready
