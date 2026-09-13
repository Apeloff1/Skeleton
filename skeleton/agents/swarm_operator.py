"""Read-only operator projections over a live swarm runtime."""

from __future__ import annotations

from dataclasses import asdict

from skeleton.agents.swarm_autoscale import AutoscalePolicy
from skeleton.agents.swarm_retention import RetentionPolicy
from skeleton.agents.swarm_runtime import SwarmRuntime


class SwarmOperator:
    def __init__(self, runtime: SwarmRuntime) -> None:
        self.runtime = runtime

    def overview(self, *, stale_after: float = 90.0) -> dict[str, object]:
        health = self.runtime.health(stale_after=stale_after)
        autoscale = AutoscalePolicy().recommend(self.runtime)
        retention = RetentionPolicy().plan(self.runtime)
        return {
            "health": health,
            "autoscale": asdict(autoscale),
            "retention": asdict(retention),
            "workers": [
                {
                    "id": worker.id,
                    "capacity": worker.capacity,
                    "active": len(worker.active),
                    "available": worker.available,
                    "completed": worker.completed,
                    "failed": worker.failed,
                }
                for worker in self.runtime.workers()
            ],
        }

    def hot_workers(self, *, utilization_at_least: float = 0.8) -> tuple[str, ...]:
        if not 0 <= utilization_at_least <= 1:
            raise ValueError("utilization threshold must be between 0 and 1")
        ids: list[str] = []
        for worker in self.runtime.workers():
            utilization = len(worker.active) / worker.capacity
            if utilization >= utilization_at_least:
                ids.append(worker.id)
        return tuple(sorted(ids))
