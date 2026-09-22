"""Pure autoscaling recommendations for swarm worker fleets."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from skeleton.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class ScaleRecommendation:
    current_slots: int
    desired_slots: int
    delta: int
    queued: int
    reason: str


@dataclass(frozen=True, slots=True)
class AutoscalePolicy:
    target_tasks_per_slot: float = 2.0
    min_slots: int = 1
    max_slots: int = 10_000

    def __post_init__(self) -> None:
        if self.target_tasks_per_slot <= 0:
            raise ValueError("target_tasks_per_slot must be positive")
        if self.min_slots < 0 or self.max_slots < self.min_slots:
            raise ValueError("invalid slot bounds")

    def recommend(self, runtime: SwarmRuntime) -> ScaleRecommendation:
        snap = runtime.snapshot()
        current = snap.available_slots + snap.leased
        demand = snap.queued + snap.leased
        desired = ceil(demand / self.target_tasks_per_slot) if demand else self.min_slots
        desired = min(self.max_slots, max(self.min_slots, desired))
        delta = desired - current
        reason = "steady"
        if delta > 0:
            reason = "queue demand exceeds target capacity"
        elif delta < 0:
            reason = "capacity exceeds target demand"
        return ScaleRecommendation(current, desired, delta, snap.queued, reason)
