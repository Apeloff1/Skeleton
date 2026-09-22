"""Thread-safe production facade for the bounded swarm runtime.

FastAPI executes synchronous handlers in a worker threadpool, so the base in-memory
runtime needs an explicit concurrency boundary when used by the HTTP control plane.
This facade centralizes that boundary and adds worker/lease limits independent of API
validation.
"""

from __future__ import annotations

from math import isfinite
from threading import RLock
from time import monotonic
from typing import Callable, Iterable, Mapping

from skeleton.agents.swarm_runtime import (
    AdmissionError,
    LeaseError,
    SwarmRuntime,
    SwarmTask,
    TaskState,
    WorkerState,
)


_TERMINAL_STATES = frozenset(
    {TaskState.SUCCEEDED, TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED}
)


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
        max_tasks = self._positive_int(max_tasks, "max_tasks")
        max_workers = self._positive_int(max_workers, "max_workers")
        default_lease_seconds = self._positive_finite(
            default_lease_seconds,
            "default_lease_seconds",
        )
        max_lease_seconds = self._positive_finite(max_lease_seconds, "max_lease_seconds")
        if default_lease_seconds > max_lease_seconds:
            raise ValueError("default lease exceeds max_lease_seconds")

        def checked_clock() -> float:
            value = clock()
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RuntimeError("swarm clock must return a finite number")
            value = float(value)
            if not isfinite(value):
                raise RuntimeError("swarm clock must return a finite number")
            return value

        super().__init__(
            max_tasks=max_tasks,
            default_lease_seconds=default_lease_seconds,
            clock=checked_clock,
        )
        self.max_workers = max_workers
        self.max_lease_seconds = max_lease_seconds
        self._lock = RLock()

    @staticmethod
    def _positive_int(value: int, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{label} must be a positive integer")
        return value

    @staticmethod
    def _nonnegative_int(value: int, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value

    @staticmethod
    def _positive_finite(value: float, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a positive finite number")
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{label} must be a positive finite number")
        return value

    @staticmethod
    def _id(value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise AdmissionError(f"{label} must not be empty")
        return normalized

    def register_worker(
        self,
        worker_id: str,
        *,
        capabilities: Iterable[str] = (),
        capacity: int = 1,
    ) -> WorkerState:
        worker_id = self._id(worker_id, "worker_id")
        capacity = self._positive_int(capacity, "capacity")
        with self._lock:
            if len(self._workers) >= self.max_workers:
                raise AdmissionError("runtime worker capacity exhausted")
            return super().register_worker(
                worker_id,
                capabilities=capabilities,
                capacity=capacity,
            )

    def heartbeat(self, worker_id: str) -> WorkerState:
        with self._lock:
            return super().heartbeat(worker_id.strip())

    def unregister_worker(self, worker_id: str, *, requeue: bool = True) -> int:
        with self._lock:
            return super().unregister_worker(worker_id.strip(), requeue=requeue)

    def submit(self, task: SwarmTask) -> SwarmTask:
        task_id = self._id(task.id, "task id")
        self._positive_int(task.max_attempts, "max_attempts")
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
                self._positive_int(task.max_attempts, "max_attempts")
                if task_id in seen:
                    raise AdmissionError(f"duplicate task id inside batch: {task_id}")
                if task_id in self._tasks:
                    raise AdmissionError(f"duplicate task id: {task_id}")
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
            return tuple(
                super(HardenedSwarmRuntime, self).submit(task) for task in normalized
            )

    def lease(self, worker_id: str, *, limit: int | None = None) -> list[SwarmTask]:
        if limit is not None:
            limit = self._nonnegative_int(limit, "limit")
        with self._lock:
            return super().lease(worker_id.strip(), limit=limit)

    def renew(
        self,
        worker_id: str,
        task_id: str,
        *,
        seconds: float | None = None,
    ) -> SwarmTask:
        duration = self.default_lease_seconds if seconds is None else self._positive_finite(
            seconds,
            "lease renewal duration",
        )
        if duration > self.max_lease_seconds:
            raise LeaseError("lease renewal exceeds max_lease_seconds")
        with self._lock:
            return super().renew(
                worker_id.strip(),
                task_id.strip(),
                seconds=duration,
            )

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
            if (
                task is not None
                and task.state is TaskState.DEAD
                and task.attempts >= task.max_attempts
                and not reset_attempts
            ):
                raise AdmissionError(
                    "dead task exhausted retry budget; reset_attempts is required"
                )
            return super().revive(task_id, reset_attempts=reset_attempts)

    def forget(self, task_id: str) -> bool:
        """Remove one terminal task and reclaim resident task capacity.

        Live queued or leased work is never silently discarded. Unknown task IDs are
        idempotent and return False, which makes retention sweeps safe to retry.
        """
        task_id = self._id(task_id, "task id")
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.state not in _TERMINAL_STATES:
                raise AdmissionError(f"cannot forget non-terminal task: {task_id}")
            del self._tasks[task_id]
            self._state_counts[task.state] -= 1
            self._event("task.forgotten", task_id)
            return True

    def reap_expired(self) -> int:
        with self._lock:
            return super().reap_expired()

    def stale_workers(self, *, stale_after: float):
        stale_after = self._positive_finite(stale_after, "stale_after")
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
        stale_after = self._positive_finite(stale_after, "stale_after")
        with self._lock:
            result = super().health(stale_after=stale_after)
            snapshot = result.get("snapshot", {})
            workers = int(snapshot.get("workers", 0))
            queued = int(snapshot.get("queued", 0))
            if result.get("status") == "critical" and queued > 0 and workers == 0:
                result["status"] = "degraded"
                result["availability"] = "awaiting_workers"
            elif workers > 0:
                result["availability"] = "available"
            else:
                result["availability"] = "idle"
            return result

    def export_state(self) -> dict[str, object]:
        with self._lock:
            state = super().export_state()
            config = dict(state.get("config", {}))
            config.update(
                {
                    "max_workers": self.max_workers,
                    "max_lease_seconds": self.max_lease_seconds,
                }
            )
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
        base = SwarmRuntime.from_state(
            validated,
            clock=runtime._clock,
            requeue_leased=requeue_leased,
        )
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
        now = runtime._clock()
        for worker in runtime._workers.values():
            worker.last_seen = now
            if requeue_leased:
                worker.active.clear()
        return runtime
