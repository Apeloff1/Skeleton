"""Cooperative worker drain and shutdown planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from typing import Callable, Sequence

from skeleton.shells.worker import QueueWorker, WorkerGroup, WorkerState


class ShutdownPhase(str, Enum):
    REQUESTED = "requested"
    DRAINING = "draining"
    STOPPED = "stopped"
    FORCED = "forced"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class ShutdownPolicy:
    max_rounds: int = 100
    deadline_seconds: float = 30.0
    drain_claimed: bool = True
    stop_on_failed_worker: bool = False

    def __post_init__(self) -> None:
        if self.max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")


@dataclass(frozen=True)
class WorkerShutdownResult:
    owner: str
    state: WorkerState
    processed: int
    stop_requested: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "state": self.state.value,
            "processed": self.processed,
            "stop_requested": self.stop_requested,
        }


@dataclass(frozen=True)
class ShutdownReport:
    phase: ShutdownPhase
    workers: tuple[WorkerShutdownResult, ...]
    rounds: int
    started_at: float
    finished_at: float
    queue_counts: dict[str, int]

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    @property
    def complete(self) -> bool:
        return self.phase is ShutdownPhase.STOPPED

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "rounds": self.rounds,
            "duration_seconds": self.duration_seconds,
            "queue_counts": dict(self.queue_counts),
            "workers": [item.to_dict() for item in self.workers],
        }


class WorkerShutdownCoordinator:
    """Drive an explicit bounded shutdown without spawning helper threads."""

    def __init__(
        self,
        workers: Sequence[QueueWorker],
        *,
        policy: ShutdownPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.workers = tuple(workers)
        if not self.workers:
            raise ValueError("at least one worker is required")
        if len({id(worker.queue) for worker in self.workers}) != 1:
            raise ValueError("shutdown workers must share a queue")
        self.queue = self.workers[0].queue
        self.policy = policy or ShutdownPolicy()
        self._clock = clock

    def shutdown(self) -> ShutdownReport:
        started = self._clock()
        processed = {worker.owner: 0 for worker in self.workers}
        rounds = 0

        # Stop future long drains but allow this coordinator to claim one item
        # at a time while within the explicit drain budget.
        for worker in self.workers:
            if worker.snapshot().state is WorkerState.FAILED and self.policy.stop_on_failed_worker:
                for member in self.workers:
                    member.request_stop()
                return self._report(ShutdownPhase.INCOMPLETE, processed, rounds, started)

        if self.policy.drain_claimed:
            for _ in range(self.policy.max_rounds):
                if self._clock() - started >= self.policy.deadline_seconds:
                    break
                rounds += 1
                progressed = False
                for worker in self.workers:
                    snapshot = worker.snapshot()
                    if snapshot.state is WorkerState.FAILED:
                        continue
                    result = worker.run_once()
                    if result is not None:
                        processed[worker.owner] += 1
                        progressed = True
                if not progressed:
                    break

        for worker in self.workers:
            worker.request_stop()

        counts = self.queue.counts()
        phase = ShutdownPhase.STOPPED
        if counts.get("claimed", 0):
            phase = ShutdownPhase.INCOMPLETE
        elif counts.get("queued", 0) and self.policy.drain_claimed:
            phase = ShutdownPhase.INCOMPLETE
        if self._clock() - started >= self.policy.deadline_seconds and phase is not ShutdownPhase.STOPPED:
            phase = ShutdownPhase.FORCED
        return self._report(phase, processed, rounds, started)

    def _report(
        self,
        phase: ShutdownPhase,
        processed: dict[str, int],
        rounds: int,
        started: float,
    ) -> ShutdownReport:
        worker_rows = tuple(
            WorkerShutdownResult(
                owner=worker.owner,
                state=worker.snapshot().state,
                processed=processed[worker.owner],
                stop_requested=worker.snapshot().stop_requested,
            )
            for worker in self.workers
        )
        return ShutdownReport(
            phase=phase,
            workers=worker_rows,
            rounds=rounds,
            started_at=started,
            finished_at=self._clock(),
            queue_counts=self.queue.counts(),
        )
