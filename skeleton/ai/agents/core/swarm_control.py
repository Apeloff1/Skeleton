"""Unified admission, idempotency, scheduling and execution control for swarms."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from skeleton.agents.swarm_admission import AdmissionDecision, AdmissionPolicy
from skeleton.agents.swarm_idempotency import IdempotencyRegistry
from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, SwarmTask
from skeleton.agents.swarm_scheduler import SwarmScheduler, WorkerScore


@dataclass(frozen=True, slots=True)
class SubmitResult:
    task: SwarmTask
    admission: AdmissionDecision
    duplicate: bool


class SwarmControlPlane:
    """Coordinates policy primitives without embedding transport or background I/O."""

    def __init__(
        self,
        runtime: SwarmRuntime,
        *,
        admission: AdmissionPolicy | None = None,
        idempotency: IdempotencyRegistry | None = None,
        scheduler: SwarmScheduler | None = None,
    ) -> None:
        self.runtime = runtime
        self.admission = admission or AdmissionPolicy()
        self.idempotency = idempotency or IdempotencyRegistry()
        self.scheduler = scheduler or SwarmScheduler()
        self._submit_lock = RLock()

    def submit(self, task: SwarmTask, *, idempotency_key: str | None = None) -> SubmitResult:
        decision = self.admission.evaluate(self.runtime, task)
        if not decision.accepted:
            raise AdmissionError(decision.reason)

        if not idempotency_key:
            return SubmitResult(self.runtime.submit(task), decision, False)

        with self._submit_lock:
            existing = self.idempotency.get(idempotency_key)
            if existing is not None:
                self.idempotency.resolve(idempotency_key, task.id, task.payload)
                resident = self.runtime.task(existing.task_id)
                if resident is None:
                    raise AdmissionError("idempotent task record exists but resident task is missing")
                return SubmitResult(resident, decision, True)

            admitted = self.runtime.submit(task)
            self.idempotency.resolve(idempotency_key, admitted.id, admitted.payload)
            return SubmitResult(admitted, decision, False)

    def rank_workers(self, task_id: str) -> tuple[WorkerScore, ...]:
        task = self.runtime.task(task_id)
        if task is None:
            raise AdmissionError(f"unknown task: {task_id}")
        return self.scheduler.rank(self.runtime, task)

    def lease_best(self, task_id: str) -> SwarmTask | None:
        task = self.runtime.task(task_id)
        if task is None:
            raise AdmissionError(f"unknown task: {task_id}")
        worker = self.scheduler.best_worker(self.runtime, task)
        if worker is None:
            return None
        leased = self.runtime.lease(worker.id, limit=1)
        return leased[0] if leased else None
