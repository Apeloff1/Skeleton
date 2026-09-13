"""Circuit-aware worker scheduling for resilient swarm dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_circuit import CircuitBreaker
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, WorkerState
from skeleton.agents.swarm_scheduler import SwarmScheduler, WorkerScore


@dataclass(frozen=True, slots=True)
class ResilientRanking:
    eligible: tuple[WorkerScore, ...]
    quarantined: tuple[str, ...]


class ResilientSwarmScheduler:
    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self.breaker = breaker or CircuitBreaker()
        self.scheduler = SwarmScheduler()

    def rank(self, runtime: SwarmRuntime, task: SwarmTask) -> ResilientRanking:
        scores = self.scheduler.rank(runtime, task)
        eligible: list[WorkerScore] = []
        quarantined: list[str] = []
        for score in scores:
            if self.breaker.allow(score.worker_id):
                eligible.append(score)
            else:
                quarantined.append(score.worker_id)
        return ResilientRanking(tuple(eligible), tuple(quarantined))

    def best_worker(self, runtime: SwarmRuntime, task: SwarmTask) -> WorkerState | None:
        ranking = self.rank(runtime, task)
        return runtime.worker(ranking.eligible[0].worker_id) if ranking.eligible else None

    def record_success(self, worker_id: str) -> None:
        self.breaker.success(worker_id)

    def record_failure(self, worker_id: str) -> None:
        self.breaker.failure(worker_id)
