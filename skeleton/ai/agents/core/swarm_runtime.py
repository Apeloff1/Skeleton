"""Deterministic, bounded orchestration primitives for large agent swarms.

The runtime separates admission, leasing, retries, recovery and health from
model execution.  It is safe to embed in API workers, tests and local tooling:
there are no threads, sockets, database clients or background tasks hidden in
this module.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from heapq import heappop, heappush
from itertools import count
from time import monotonic
from typing import Callable, Deque, Iterable, Iterator, Mapping


class TaskState(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


class AdmissionError(ValueError):
    """Raised when a task or worker violates runtime admission invariants."""


class LeaseError(RuntimeError):
    """Raised when an invalid worker attempts to mutate a live lease."""


@dataclass(frozen=True, slots=True)
class SwarmTask:
    id: str
    payload: Mapping[str, object]
    priority: int = 100
    max_attempts: int = 3
    required_capabilities: frozenset[str] = frozenset()
    state: TaskState = TaskState.QUEUED
    attempts: int = 0
    leased_to: str | None = None
    lease_deadline: float | None = None
    last_error: str | None = None


@dataclass(slots=True)
class WorkerState:
    id: str
    capabilities: frozenset[str]
    capacity: int = 1
    active: set[str] = field(default_factory=set)
    accepted: int = 0
    completed: int = 0
    failed: int = 0
    renewals: int = 0
    heartbeats: int = 0
    last_seen: float = field(default_factory=monotonic)

    @property
    def available(self) -> int:
        return max(0, self.capacity - len(self.active))


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    queued: int
    leased: int
    succeeded: int
    failed: int
    dead: int
    cancelled: int
    workers: int
    available_slots: int
    submitted: int
    retries: int
    expired_leases: int
    lease_renewals: int
    heartbeats: int
    revived: int


class SwarmRuntime:
    """In-memory control plane for bounded multi-agent task execution."""

    def __init__(
        self,
        *,
        max_tasks: int = 100_000,
        default_lease_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_tasks < 1:
            raise ValueError("max_tasks must be positive")
        if default_lease_seconds <= 0:
            raise ValueError("default_lease_seconds must be positive")
        self.max_tasks = max_tasks
        self.default_lease_seconds = default_lease_seconds
        self._clock = clock
        self._sequence = count()
        self._queue: list[tuple[int, int, str]] = []
        self._tasks: dict[str, SwarmTask] = {}
        self._workers: dict[str, WorkerState] = {}
        self._state_counts: dict[TaskState, int] = defaultdict(int)
        self._events: Deque[tuple[float, str, str]] = deque(maxlen=10_000)
        self._submitted = 0
        self._retries = 0
        self._expired_leases = 0
        self._lease_renewals = 0
        self._heartbeats = 0
        self._revived = 0

    def register_worker(
        self, worker_id: str, *, capabilities: Iterable[str] = (), capacity: int = 1
    ) -> WorkerState:
        worker_id = worker_id.strip()
        if not worker_id:
            raise AdmissionError("worker_id must not be empty")
        if worker_id in self._workers:
            raise AdmissionError(f"duplicate worker id: {worker_id}")
        if capacity < 1:
            raise AdmissionError("capacity must be positive")
        state = WorkerState(worker_id, frozenset(capabilities), capacity, last_seen=self._clock())
        self._workers[worker_id] = state
        self._event("worker.registered", worker_id)
        return state

    def heartbeat(self, worker_id: str) -> WorkerState:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        worker.last_seen = self._clock()
        worker.heartbeats += 1
        self._heartbeats += 1
        self._event("worker.heartbeat", worker_id)
        return worker

    def unregister_worker(self, worker_id: str, *, requeue: bool = True) -> int:
        worker = self._workers.pop(worker_id, None)
        if worker is None:
            return 0
        released = 0
        for task_id in tuple(worker.active):
            task = self._tasks.get(task_id)
            if task is None or task.state is not TaskState.LEASED:
                continue
            released += 1
            self._transition(task, TaskState.QUEUED if requeue else TaskState.DEAD)
            if requeue:
                self._requeue(task_id)
        self._event("worker.unregistered", worker_id)
        return released

    def submit(self, task: SwarmTask) -> SwarmTask:
        if len(self._tasks) >= self.max_tasks:
            raise AdmissionError("runtime task capacity exhausted")
        if not task.id.strip():
            raise AdmissionError("task id must not be empty")
        if task.id in self._tasks:
            raise AdmissionError(f"duplicate task id: {task.id}")
        if task.max_attempts < 1:
            raise AdmissionError("max_attempts must be positive")
        admitted = replace(task, state=TaskState.QUEUED, attempts=0, leased_to=None, lease_deadline=None, last_error=None)
        self._tasks[admitted.id] = admitted
        self._state_counts[TaskState.QUEUED] += 1
        self._submitted += 1
        self._requeue(admitted.id)
        self._event("task.submitted", admitted.id)
        return admitted

    def lease(self, worker_id: str, *, limit: int | None = None) -> list[SwarmTask]:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        worker.last_seen = self._clock()
        budget = worker.available if limit is None else min(worker.available, max(0, limit))
        if budget == 0:
            return []
        leased: list[SwarmTask] = []
        deferred: list[tuple[int, int, str]] = []
        while self._queue and len(leased) < budget:
            item = heappop(self._queue)
            _, _, task_id = item
            task = self._tasks.get(task_id)
            if task is None or task.state is not TaskState.QUEUED:
                continue
            if not task.required_capabilities.issubset(worker.capabilities):
                deferred.append(item)
                continue
            updated = replace(
                task,
                state=TaskState.LEASED,
                attempts=task.attempts + 1,
                leased_to=worker_id,
                lease_deadline=self._clock() + self.default_lease_seconds,
            )
            self._replace(task, updated)
            worker.active.add(task_id)
            worker.accepted += 1
            leased.append(updated)
            self._event("task.leased", task_id)
        for item in deferred:
            heappush(self._queue, item)
        return leased

    def renew(self, worker_id: str, task_id: str, *, seconds: float | None = None) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id)
        duration = self.default_lease_seconds if seconds is None else seconds
        if duration <= 0:
            raise LeaseError("lease renewal duration must be positive")
        updated = replace(task, lease_deadline=self._clock() + duration)
        self._replace(task, updated)
        worker.last_seen = self._clock()
        worker.renewals += 1
        self._lease_renewals += 1
        self._event("task.lease_renewed", task_id)
        return updated

    def succeed(self, worker_id: str, task_id: str) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id)
        updated = replace(task, state=TaskState.SUCCEEDED, leased_to=None, lease_deadline=None)
        self._replace(task, updated)
        worker.active.discard(task_id)
        worker.completed += 1
        worker.last_seen = self._clock()
        self._event("task.succeeded", task_id)
        return updated

    def fail(self, worker_id: str, task_id: str, error: str) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id)
        retry = task.attempts < task.max_attempts
        updated = replace(
            task,
            state=TaskState.QUEUED if retry else TaskState.DEAD,
            leased_to=None,
            lease_deadline=None,
            last_error=error[:2_000],
        )
        self._replace(task, updated)
        worker.active.discard(task_id)
        worker.failed += 1
        worker.last_seen = self._clock()
        if retry:
            self._retries += 1
            self._requeue(task_id)
            self._event("task.retried", task_id)
        else:
            self._event("task.dead", task_id)
        return updated

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> SwarmTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise AdmissionError(f"unknown task: {task_id}")
        if task.state in {TaskState.SUCCEEDED, TaskState.CANCELLED}:
            return task
        if task.state is TaskState.LEASED and task.leased_to:
            worker = self._workers.get(task.leased_to)
            if worker is not None:
                worker.active.discard(task_id)
        updated = replace(task, state=TaskState.CANCELLED, leased_to=None, lease_deadline=None, last_error=reason[:2_000])
        self._replace(task, updated)
        self._event("task.cancelled", task_id)
        return updated

    def revive(self, task_id: str, *, reset_attempts: bool = False) -> SwarmTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise AdmissionError(f"unknown task: {task_id}")
        if task.state not in {TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED}:
            raise AdmissionError(f"task is not recoverable: {task_id}")
        updated = replace(
            task,
            state=TaskState.QUEUED,
            attempts=0 if reset_attempts else task.attempts,
            leased_to=None,
            lease_deadline=None,
            last_error=None,
        )
        self._replace(task, updated)
        self._requeue(task_id)
        self._revived += 1
        self._event("task.revived", task_id)
        return updated

    def reap_expired(self) -> int:
        now = self._clock()
        expired = [task for task in self._tasks.values() if task.state is TaskState.LEASED and task.lease_deadline is not None and task.lease_deadline <= now]
        for task in expired:
            worker = self._workers.get(task.leased_to or "")
            if worker is not None:
                worker.active.discard(task.id)
            retry = task.attempts < task.max_attempts
            updated = replace(
                task,
                state=TaskState.QUEUED if retry else TaskState.DEAD,
                leased_to=None,
                lease_deadline=None,
                last_error="lease expired",
            )
            self._replace(task, updated)
            if retry:
                self._retries += 1
                self._requeue(task.id)
            self._expired_leases += 1
            self._event("task.lease_expired", task.id)
        return len(expired)

    def stale_workers(self, *, stale_after: float) -> tuple[WorkerState, ...]:
        if stale_after <= 0:
            raise ValueError("stale_after must be positive")
        cutoff = self._clock() - stale_after
        return tuple(worker for worker in self._workers.values() if worker.last_seen <= cutoff)

    def health(self, *, stale_after: float = 90.0) -> dict[str, object]:
        snapshot = self.snapshot()
        stale = self.stale_workers(stale_after=stale_after)
        saturation = 0.0
        total_slots = snapshot.available_slots + snapshot.leased
        if total_slots:
            saturation = snapshot.leased / total_slots
        queue_pressure = snapshot.queued / max(1, snapshot.available_slots)
        status = "healthy"
        if snapshot.dead > 0 or stale:
            status = "degraded"
        if snapshot.workers == 0 and snapshot.queued > 0:
            status = "critical"
        return {
            "status": status,
            "stale_workers": [worker.id for worker in stale],
            "worker_saturation": round(saturation, 6),
            "queue_pressure": round(queue_pressure, 6),
            "snapshot": asdict(snapshot),
        }

    def task(self, task_id: str) -> SwarmTask | None:
        return self._tasks.get(task_id)

    def worker(self, worker_id: str) -> WorkerState | None:
        return self._workers.get(worker_id)

    def pending(self) -> Iterator[SwarmTask]:
        return (task for task in self._tasks.values() if task.state is TaskState.QUEUED)

    def dead(self) -> Iterator[SwarmTask]:
        return (task for task in self._tasks.values() if task.state is TaskState.DEAD)

    def tasks(self) -> tuple[SwarmTask, ...]:
        return tuple(self._tasks.values())

    def workers(self) -> tuple[WorkerState, ...]:
        return tuple(self._workers.values())

    def events(self) -> tuple[tuple[float, str, str], ...]:
        return tuple(self._events)

    def export_state(self) -> dict[str, object]:
        return {
            "version": 1,
            "config": {"max_tasks": self.max_tasks, "default_lease_seconds": self.default_lease_seconds},
            "tasks": [self._task_record(task) for task in self._tasks.values()],
            "workers": [self._worker_record(worker) for worker in self._workers.values()],
            "counters": {
                "submitted": self._submitted,
                "retries": self._retries,
                "expired_leases": self._expired_leases,
                "lease_renewals": self._lease_renewals,
                "heartbeats": self._heartbeats,
                "revived": self._revived,
            },
        }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, object],
        *,
        clock: Callable[[], float] = monotonic,
        requeue_leased: bool = True,
    ) -> "SwarmRuntime":
        config = state.get("config", {})
        if not isinstance(config, Mapping):
            raise ValueError("invalid runtime state config")
        runtime = cls(
            max_tasks=int(config.get("max_tasks", 100_000)),
            default_lease_seconds=float(config.get("default_lease_seconds", 30.0)),
            clock=clock,
        )
        tasks = state.get("tasks", [])
        if not isinstance(tasks, list):
            raise ValueError("invalid runtime task state")
        for raw in tasks:
            if not isinstance(raw, Mapping):
                raise ValueError("invalid task record")
            task = SwarmTask(
                id=str(raw["id"]),
                payload=dict(raw.get("payload", {})),
                priority=int(raw.get("priority", 100)),
                max_attempts=int(raw.get("max_attempts", 3)),
                required_capabilities=frozenset(raw.get("required_capabilities", ())),
                state=TaskState(str(raw.get("state", TaskState.QUEUED.value))),
                attempts=int(raw.get("attempts", 0)),
                leased_to=raw.get("leased_to") if raw.get("leased_to") is None else str(raw.get("leased_to")),
                lease_deadline=None if raw.get("lease_deadline") is None else float(raw.get("lease_deadline")),
                last_error=raw.get("last_error") if raw.get("last_error") is None else str(raw.get("last_error")),
            )
            if task.state is TaskState.LEASED and requeue_leased:
                task = replace(task, state=TaskState.QUEUED, leased_to=None, lease_deadline=None, last_error="restored lease requeued")
            runtime._tasks[task.id] = task
            runtime._state_counts[task.state] += 1
            if task.state is TaskState.QUEUED:
                runtime._requeue(task.id)
        workers = state.get("workers", [])
        if isinstance(workers, list):
            for raw in workers:
                if not isinstance(raw, Mapping):
                    continue
                worker = WorkerState(
                    id=str(raw["id"]),
                    capabilities=frozenset(raw.get("capabilities", ())),
                    capacity=int(raw.get("capacity", 1)),
                    active=set() if requeue_leased else set(raw.get("active", ())),
                    accepted=int(raw.get("accepted", 0)),
                    completed=int(raw.get("completed", 0)),
                    failed=int(raw.get("failed", 0)),
                    renewals=int(raw.get("renewals", 0)),
                    heartbeats=int(raw.get("heartbeats", 0)),
                    last_seen=float(raw.get("last_seen", clock())),
                )
                runtime._workers[worker.id] = worker
        counters = state.get("counters", {})
        if isinstance(counters, Mapping):
            runtime._submitted = int(counters.get("submitted", len(runtime._tasks)))
            runtime._retries = int(counters.get("retries", 0))
            runtime._expired_leases = int(counters.get("expired_leases", 0))
            runtime._lease_renewals = int(counters.get("lease_renewals", 0))
            runtime._heartbeats = int(counters.get("heartbeats", 0))
            runtime._revived = int(counters.get("revived", 0))
        runtime._event("runtime.restored", str(len(runtime._tasks)))
        return runtime

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            queued=self._state_counts[TaskState.QUEUED],
            leased=self._state_counts[TaskState.LEASED],
            succeeded=self._state_counts[TaskState.SUCCEEDED],
            failed=self._state_counts[TaskState.FAILED],
            dead=self._state_counts[TaskState.DEAD],
            cancelled=self._state_counts[TaskState.CANCELLED],
            workers=len(self._workers),
            available_slots=sum(worker.available for worker in self._workers.values()),
            submitted=self._submitted,
            retries=self._retries,
            expired_leases=self._expired_leases,
            lease_renewals=self._lease_renewals,
            heartbeats=self._heartbeats,
            revived=self._revived,
        )

    def _owned_lease(self, worker_id: str, task_id: str) -> tuple[SwarmTask, WorkerState]:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        task = self._tasks.get(task_id)
        if task is None or task.state is not TaskState.LEASED:
            raise LeaseError(f"task is not leased: {task_id}")
        if task.leased_to != worker_id:
            raise LeaseError(f"task {task_id} is leased to {task.leased_to}")
        return task, worker

    def _requeue(self, task_id: str) -> None:
        task = self._tasks[task_id]
        heappush(self._queue, (task.priority, next(self._sequence), task_id))

    def _transition(self, task: SwarmTask, state: TaskState) -> SwarmTask:
        updated = replace(task, state=state, leased_to=None, lease_deadline=None)
        self._replace(task, updated)
        worker = self._workers.get(task.leased_to or "")
        if worker is not None:
            worker.active.discard(task.id)
        return updated

    def _replace(self, old: SwarmTask, new: SwarmTask) -> None:
        if old.state is not new.state:
            self._state_counts[old.state] -= 1
            self._state_counts[new.state] += 1
        self._tasks[new.id] = new

    def _event(self, kind: str, subject: str) -> None:
        self._events.append((self._clock(), kind, subject))

    @staticmethod
    def _task_record(task: SwarmTask) -> dict[str, object]:
        record = asdict(task)
        record["state"] = task.state.value
        record["required_capabilities"] = sorted(task.required_capabilities)
        record["payload"] = dict(task.payload)
        return record

    @staticmethod
    def _worker_record(worker: WorkerState) -> dict[str, object]:
        return {
            "id": worker.id,
            "capabilities": sorted(worker.capabilities),
            "capacity": worker.capacity,
            "active": sorted(worker.active),
            "accepted": worker.accepted,
            "completed": worker.completed,
            "failed": worker.failed,
            "renewals": worker.renewals,
            "heartbeats": worker.heartbeats,
            "last_seen": worker.last_seen,
        }
