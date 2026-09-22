"""Service-level objective evaluation for swarm control-plane health."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class SLOPolicy:
    max_dead_ratio: float = 0.01
    max_queue_per_slot: float = 50.0
    min_available_slots: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.max_dead_ratio <= 1:
            raise ValueError("max_dead_ratio must be between 0 and 1")
        if self.max_queue_per_slot <= 0:
            raise ValueError("max_queue_per_slot must be positive")
        if self.min_available_slots < 0:
            raise ValueError("min_available_slots must be non-negative")

    def evaluate(self, runtime: SwarmRuntime) -> dict[str, object]:
        snap = runtime.snapshot()
        terminal = snap.succeeded + snap.dead + snap.cancelled + snap.failed
        dead_ratio = snap.dead / max(1, terminal)
        queue_per_slot = snap.queued / max(1, snap.available_slots)
        checks = {
            "dead_ratio": dead_ratio <= self.max_dead_ratio,
            "queue_pressure": queue_per_slot <= self.max_queue_per_slot,
            "available_slots": snap.available_slots >= self.min_available_slots or snap.queued == 0,
        }
        return {
            "met": all(checks.values()),
            "checks": checks,
            "dead_ratio": round(dead_ratio, 6),
            "queue_per_slot": round(queue_per_slot, 6),
        }
