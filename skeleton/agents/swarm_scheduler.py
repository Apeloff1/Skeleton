"""Deterministic worker ranking and scheduling diagnostics for swarm execution."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, WorkerState


@dataclass(frozen=True, slots=True)
class WorkerScore:
    worker_id: str
    score: float
    available: int
    capability_surplus: int
    success_ratio: float


class SwarmScheduler:
    """Ranks eligible workers without mutating runtime state."""

    def rank(self, runtime: SwarmRuntime, task: SwarmTask) -> tuple[WorkerScore, ...]:
        ranked: list[WorkerScore] = []
        for worker in runtime.workers():
            if not task.required_capabilities.issubset(worker.capabilities) or worker.available <= 0:
                continue
            ranked.append(self._score(worker, task))
        ranked.sort(key=lambda item: (-item.score, item.worker_id))
        return tuple(ranked)

    def best_worker(self, runtime: SwarmRuntime, task: SwarmTask) -> WorkerState | None:
        ranked = self.rank(runtime, task)
        return runtime.worker(ranked[0].worker_id) if ranked else None

    @staticmethod
    def _score(worker: WorkerState, task: SwarmTask) -> WorkerScore:
        terminal = worker.completed + worker.failed
        success_ratio = worker.completed / terminal if terminal else 1.0
        surplus = len(worker.capabilities - task.required_capabilities)
        utilization = len(worker.active) / worker.capacity
        score = (success_ratio * 100.0) + (worker.available * 5.0) - (utilization * 20.0) - (surplus * 0.1)
        return WorkerScore(worker.id, round(score, 6), worker.available, surplus, round(success_ratio, 6))
