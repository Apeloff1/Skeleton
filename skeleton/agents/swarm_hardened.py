"""Thread-safe production facade for the bounded swarm runtime.

FastAPI executes synchronous handlers in a worker threadpool, so the base in-memory
runtime needs an explicit concurrency boundary when used by the HTTP control plane.
This facade centralizes that boundary and adds worker/lease limits independent of API
validation.
"""

from __future__ import annotations

from threading import RLock
from time import monotonic
from typing import Callable, Iterable, Mapping

from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask, TaskState, WorkerState


class HardenedSwarmRuntime(SwarmRuntime):
    def __init__(
        self,
        *,
        max_tasks: int = 100_000,
        max_workers: int = 10_000,
        default_lease_seconds: float = 30.0,
        max_lease_seconds: float = 86_400.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        if max_lease_seconds <= 0:
            raise ValueError("max_lease_seconds must be positive")
        if default_lease_seconds > max_lease_seconds:
            raise ValueError("default lease exceeds max_lease_seconds")
        super().__init__(max_tasks=max_tasks, default_lease_seconds=default_lease_seconds, clock=clock)
        self.max_workers = max_workers
        self.max_lease_seconds = max_lease_seconds
        self._lock = RLock()

    @staticmethod
    def _id(value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise AdmissionError(f"{label} must not be empty")
        return normalized

    def register_worker(self, worker_id: str, *, capabilities: Iterable[str] = (), capacity: int = 1) -> WorkerState:
        worker_id = self._id(worker_id, "worker_id")
        with self._lock:
            if len(self._workers) >= self.max_workers:
                raise AdmissionError("runtime worker capacity exhausted")
            return super().register_worker(worker_id, capabilities=capabilities, capacity=capacity)

    def heartbeat(self, worker_id: str) -> WorkerState:
        with self._lock:
            return super().heartbeat(worker_id.strip())

    def unregister_worker(self, worker_id: str, *, requeue: bool = True) -> int:
        with self._lock:
            return super().unregister_worker(worker_id.strip(), requeue=requeue)

    def submit(self, task: SwarmTask) -> SwarmTask:
        task_id = self._id(task.id, "task id")
        if task_id != task.id:
            task = SwarmTask(
                id=task_id,
                payload=task.payload,
                priority=task.priority,
                max_attempts=task.max_attempts,
                required_capabilities=task.required_capabilities,
            )
        with self._lock:
            return super().submit(task)

    def submit_many(self, tasks: Iterable[SwarmTask]) -> tuple[SwarmTask, ...]:
        """Atomically preflight and admit a complete task batch under one runtime lock."""
        batch = tuple(tasks)
        normalized: list[SwarmTask] = []
        seen: set[str] = set()
        with self._lock:
            if len(self._tasks) + len(batch) > self.max_tasks:
                raise AdmissionError("batch exceeds runtime task capacity")
            for task in batch:
                task_id = self._id(task.id, "task id")
                if task_id in seen:
                    raise AdmissionError(f"duplicate task id inside batch: {task_id}")
                if task_id in self._tasks:
                    raise AdmissionError(f"duplicate task id: {task_id}")
                if task.max_attempts < 1:
                    raise AdmissionError("max_attempts must be positive")
                seen.add(task_id)
                normalized.append(
                    task
                    if task_id == task.id
                    else SwarmTask(
                        id=task_id,
                        payload=task.payload,
                        priority=task.priority,
                        max_attempts=task.max_attempts,
                        required_capabilities=task.required_capabilities,
                    )
                )
            return tuple(super(HardenedSwarmRuntime, self).submit(task) for task in normalized)

    def lease(self, worker_id: str, *, limit: int | None = None) -> list[SwarmTask]:
        with self._lock:
            return super().lease(worker_id.strip(), limit=limit)

    def renew(self, worker_id: str, task_id: str, *, seconds: float | None = None) -> SwarmTask:
        duration = self.default_lease_seconds if seconds is None else seconds
        if duration > self.max_lease_seconds:
            raise LeaseError("lease renewal exceeds max_lease_seconds")
        with self._lock:
            return super().renew(worker_id.strip(), task_id.strip(), seconds=duration)

    def succeed(self, worker_id: str, task_id: str) -> SwarmTask:
        with self._lock:
            return super().succeed(worker_id.strip(), task_id.strip())

    def fail(self, worker_id: str, task_id: str, error: str) -> SwarmTask:
        with self._lock:
            return super().fail(worker_id.strip(), task_id.strip(), error)

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> SwarmTask:
        with self._lock:
            return super().cancel(task_id.strip(), reason=reason)

    def revive(self, task_id: str, *, reset_attempts: bool = False) -> SwarmTask:
        task_id = task_id.strip()
        with self._lock:
            task = super().task(task_id)
            if task is not None and task.state is TaskState.DEAD and task.attempts >= task.max_attempts and not reset_attempts:
                raise AdmissionError("dead task exhausted retry budget; reset_attempts is required")
            return super().revive(task_id, reset_attempts=reset_attempts)

    def reap_expired(self) -> int:
        with self._lock:
            return super().reap_expired()

    def stale_workers(self, *, stale_after: float):
        with self._lock:
            return super().stale_workers(stale_after=stale_after)

    def task(self, task_id: str):
        with self._lock:
            return super().task(task_id.strip())

    def worker(self, worker_id: str):
        with self._lock:
            return super().worker(worker_id.strip())

    def pending(self):
        with self._lock:
            return iter(tuple(super().pending()))

    def dead(self):
        with self._lock:
            return iter(tuple(super().dead()))

    def tasks(self):
        with self._lock:
            return super().tasks()

    def workers(self):
        with self._lock:
            return super().workers()

    def events(self):
        with self._lock:
            return super().events()

    def snapshot(self):
        with self._lock:
            return super().snapshot()

    def health(self, *, stale_after: float = 90.0):
        with self._lock:
            return super().health(stale_after=stale_after)

    def export_state(self) -> dict[str, object]:
        with self._lock:
            state = super().export_state()
            config = dict(state.get("config", {}))
            config.update({"max_workers": self.max_workers, "max_lease_seconds": self.max_lease_seconds})
            state["config"] = config
            return state

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, object],
        *,
        clock: Callable[[], float] = monotonic,
        requeue_leased: bool = True,
    ) -> "HardenedSwarmRuntime":
        from skeleton.agents.swarm_restore import validate_restore_state

        validated = validate_restore_state(state)
        config = validated["config"]
        runtime = cls(
            max_tasks=int(config.get("max_tasks", 100_000)),
            max_workers=int(config.get("max_workers", 10_000)),
            default_lease_seconds=float(config.get("default_lease_seconds", 30.0)),
            max_lease_seconds=float(config.get("max_lease_seconds", 86_400.0)),
            clock=clock,
        )
        base = SwarmRuntime.from_state(validated, clock=clock, requeue_leased=requeue_leased)
        runtime._sequence = base._sequence
        runtime._queue = base._queue
        runtime._tasks = base._tasks
        runtime._workers = base._workers
        runtime._state_counts = base._state_counts
        runtime._events = base._events
        runtime._submitted = base._submitted
        runtime._retries = base._retries
        runtime._expired_leases = base._expired_leases
        runtime._lease_renewals = base._lease_renewals
        runtime._heartbeats = base._heartbeats
        runtime._revived = base._revived
        now = clock()
        for worker in runtime._workers.values():
            worker.last_seen = now
            if requeue_leased:
                worker.active.clear()
        return runtime
