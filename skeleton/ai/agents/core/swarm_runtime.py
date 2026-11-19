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
import math
from uuid import uuid4
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
    dependencies: tuple[str, ...] = ()
    lease_token: str | None = None
    effect_uncertain: bool = False
    reconciliation_sha256: str | None = None
    wait_intent_sha256: str | None = None
    wake_receipt_sha256: str | None = None
    singleton_scope_sha256: str | None = None


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
    parent_id: str | None = None
    delegated_capacity: int = 0
    registration_token: str = field(default_factory=lambda: uuid4().hex)

    @property
    def available(self) -> int:
        return max(0, self.capacity - self.delegated_capacity - len(self.active))


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
        fenced: bool = False,
    ) -> None:
        if type(fenced) is not bool:
            raise ValueError("fenced must be boolean")
        if type(max_tasks) is not int or max_tasks < 1:
            raise ValueError("max_tasks must be positive")
        if not math.isfinite(default_lease_seconds) or default_lease_seconds <= 0:
            raise ValueError("default_lease_seconds must be positive")
        self.max_tasks = max_tasks
        self.default_lease_seconds = default_lease_seconds
        self._clock = clock
        self.fenced = fenced
        self._queued_generation: dict[str, int] = {}
        self._sequence = count()
        self._queue: list[tuple[int, int, str]] = []
        self._tasks: dict[str, SwarmTask] = {}
        self._singleton_holders: dict[str, str] = {}
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

    def worker_lineage(self, worker_id: str) -> tuple[str, ...]:
        """Return worker-to-root identities, never a transport credential."""
        result: list[str] = []
        current: str | None = worker_id
        while current is not None:
            if current in result or len(result) >= 9:
                raise LeaseError("invalid worker hierarchy")
            worker = self._workers.get(current)
            if worker is None:
                raise LeaseError("missing worker hierarchy owner")
            result.append(current)
            current = worker.parent_id
        return tuple(result)

    def register_virtual_worker(self, worker_id: str, parent_id: str, *,
                                capabilities: Iterable[str], capacity: int = 1) -> WorkerState:
        """Partition real logical capacity; a virtual child creates no new slots.

        Only the existing trusted owner may register workers. Child capability
        declarations may narrow but never enlarge their parent's authority.
        This is logical capacity partitioning, not physical worker discovery.
        """
        if not self.fenced:
            raise AdmissionError("virtual workers require fenced execution mode")
        if type(worker_id) is not str or not worker_id or worker_id != worker_id.strip():
            raise AdmissionError("invalid virtual worker identity")
        if type(parent_id) is not str or parent_id != parent_id.strip():
            raise AdmissionError("invalid parent identity")
        if worker_id in self._workers or type(capacity) is not int or capacity < 1:
            raise AdmissionError("duplicate virtual worker or invalid capacity")
        parent = self._workers.get(parent_id)
        if parent is None or capacity > parent.available or len(self.worker_lineage(parent_id)) >= 9:
            raise AdmissionError("parent capacity or depth exhausted")
        if isinstance(capabilities, (str, bytes)):
            raise AdmissionError("invalid child capability set")
        declared = frozenset(capabilities)
        if not declared <= parent.capabilities:
            raise AdmissionError("child capability escalation")
        # register_worker is the existing hardened max-worker admission point.
        child = self.register_worker(worker_id, capabilities=declared, capacity=capacity)
        child.parent_id = parent_id
        parent.delegated_capacity += capacity
        return child

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
        worker = self._workers.get(worker_id)
        if worker is not None and worker.delegated_capacity:
            raise LeaseError("remove virtual descendants before their parent")
        if self.fenced and worker is not None and worker.active:
            raise LeaseError("active or uncertain work must be reconciled before worker removal")
        if worker is not None and worker.parent_id is not None:
            parent = self._workers.get(worker.parent_id)
            if parent is None or parent.delegated_capacity < worker.capacity:
                raise LeaseError("invalid virtual capacity custody")
            parent.delegated_capacity -= worker.capacity
        worker = self._workers.pop(worker_id, None)
        if worker is None:
            return 0
        released = 0
        for task_id in tuple(worker.active):
            task = self._tasks.get(task_id)
            if task is None or task.state is not TaskState.LEASED:
                continue
            released += 1
            retry = requeue and task.attempts < task.max_attempts
            self._transition(task, TaskState.QUEUED if retry else TaskState.DEAD)
            if retry:
                self._requeue(task_id)
        self._event("worker.unregistered", worker_id)
        return released

    @staticmethod
    def _validate_dispatch_metadata(task: SwarmTask, *, fenced: bool, restoring: bool = False) -> None:
        fields = (task.wait_intent_sha256, task.wake_receipt_sha256, task.singleton_scope_sha256)
        if any(value is not None for value in fields) and not fenced:
            raise AdmissionError("dispatch gates require fenced execution")
        if any(value is not None and (type(value) is not str or len(value) != 64
               or any(c not in "0123456789abcdef" for c in value)) for value in fields):
            raise AdmissionError("invalid dispatch metadata digest")
        if task.wake_receipt_sha256 is not None and (not restoring or task.wait_intent_sha256 is None):
            raise AdmissionError("wake receipt requires trusted gated transition")
        if restoring and (task.state is TaskState.LEASED or task.effect_uncertain or task.attempts > 0):
            if task.wait_intent_sha256 is not None and task.wake_receipt_sha256 is None:
                raise AdmissionError("attempt without a verified wake receipt")

    def dispatch_blocked(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            raise AdmissionError("unknown dispatch task")
        scope = task.singleton_scope_sha256
        return ((task.wait_intent_sha256 is not None and task.wake_receipt_sha256 is None)
                or (scope is not None and self._singleton_holders.get(scope) not in (None, task_id))
                or bool(self.blocked_dependencies(task_id)))

    def open_wait(self, task_id: str, *, intent_sha256: str, receipt_sha256: str) -> SwarmTask:
        """Trusted owner only; the durable bridge independently verifies receipt evidence."""
        task = self._tasks.get(task_id)
        if (not self.fenced or task is None or task.wait_intent_sha256 != intent_sha256
                or intent_sha256 is None or type(receipt_sha256) is not str
                or len(receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in receipt_sha256)):
            raise AdmissionError("wait identity or receipt mismatch")
        if task.wake_receipt_sha256 is not None:
            if task.wake_receipt_sha256 != receipt_sha256:
                raise AdmissionError("wait receipt identity conflict")
            return task
        if task.state is not TaskState.QUEUED or task.effect_uncertain or task.attempts:
            raise AdmissionError("wait no longer eligible")
        updated = replace(task, wake_receipt_sha256=receipt_sha256)
        self._replace(task, updated)
        return updated

    def submit(self, task: SwarmTask) -> SwarmTask:
        self._validate_dispatch_metadata(task, fenced=self.fenced)
        if len(self._tasks) >= self.max_tasks:
            raise AdmissionError("runtime task capacity exhausted")
        if type(task.id) is not str or not task.id.strip() or task.id != task.id.strip():
            raise AdmissionError("task id must be canonical nonempty text")
        if type(task.priority) is not int or not 0 <= task.priority <= 1000:
            raise AdmissionError("invalid task priority")
        if task.id in self._tasks:
            raise AdmissionError(f"duplicate task id: {task.id}")
        if type(task.max_attempts) is not int or not 1 <= task.max_attempts <= 1000:
            raise AdmissionError("max_attempts must be an integer in [1, 1000]")
        if type(task.dependencies) is not tuple or len(task.dependencies) > 256 or any(
            type(dep) is not str or not dep or dep not in self._tasks for dep in task.dependencies
        ) or len(set(task.dependencies)) != len(task.dependencies):
            raise AdmissionError("dependencies require distinct previously submitted tasks")
        admitted = replace(task, state=TaskState.QUEUED, attempts=0, leased_to=None,
                           lease_deadline=None, last_error=None, lease_token=None, effect_uncertain=False,
                           reconciliation_sha256=None)
        self._tasks[admitted.id] = admitted
        self._state_counts[TaskState.QUEUED] += 1
        self._submitted += 1
        self._requeue(admitted.id)
        self._event("task.submitted", admitted.id)
        return admitted

    def submit_graph(self, tasks: tuple[SwarmTask, ...]) -> tuple[SwarmTask, ...]:
        """Topologically admit a bounded graph into this existing queue.

        All inputs are validated before publication; existing dependencies may
        be referenced, but cycles and unknown parents are rejected. No task
        payload grants worker or tool authority. This runtime is single-owner
        and synchronous, so commit does not race another runtime operation.
        """
        from graphlib import TopologicalSorter, CycleError

        if type(tasks) is not tuple or not 1 <= len(tasks) <= 4096:
            raise AdmissionError("invalid graph size")
        if len(tasks) + len(self._tasks) > self.max_tasks:
            raise AdmissionError("runtime task capacity exhausted")
        by_id: dict[str, SwarmTask] = {}
        for task in tasks:
            if (not isinstance(task, SwarmTask) or type(task.id) is not str or not task.id.strip()
                    or task.id != task.id.strip()):
                raise AdmissionError("invalid graph node")
            if task.id in by_id or task.id in self._tasks:
                raise AdmissionError("duplicate graph node")
            if type(task.max_attempts) is not int or not 1 <= task.max_attempts <= 1000:
                raise AdmissionError("invalid attempt budget")
            if type(task.dependencies) is not tuple or len(task.dependencies) > 256 or any(
                type(dep) is not str or not dep for dep in task.dependencies
            ) or len(set(task.dependencies)) != len(task.dependencies):
                raise AdmissionError("invalid graph predecessors")
            if type(task.priority) is not int or not 0 <= task.priority <= 1000:
                raise AdmissionError("invalid graph priority")
            self._validate_dispatch_metadata(task, fenced=self.fenced)
            by_id[task.id] = task
        if sum(len(t.dependencies) for t in tasks) > 65_536:
            raise AdmissionError("graph edge limit exceeded")
        for task in tasks:
            if any(dep not in by_id and dep not in self._tasks for dep in task.dependencies):
                raise AdmissionError("unresolved graph dependency")
        sorter = TopologicalSorter({
            task.id: tuple(sorted(dep for dep in task.dependencies if dep in by_id))
            for task in sorted(tasks, key=lambda t: t.id)
        })
        try:
            order = tuple(sorter.static_order())
        except CycleError as exc:
            raise AdmissionError("graph contains a cycle") from exc
        return tuple(self.submit(by_id[task_id]) for task_id in order)

    def blocked_dependencies(self, task_id: str) -> tuple[str, ...]:
        """Inspect blockers without mutating or executing unrelated work."""
        task = self._tasks.get(task_id)
        if task is None:
            raise AdmissionError("unknown task")
        return tuple(dep for dep in task.dependencies
                     if self._tasks[dep].state is not TaskState.SUCCEEDED)

    def cancel_failed_dependents(self, *, limit: int = 4096) -> tuple[str, ...]:
        """Explicitly propagate terminal dependency failures; uncertain effects hold."""
        if type(limit) is not int or not 1 <= limit <= 4096:
            raise AdmissionError("invalid dependency propagation limit")
        cancelled: list[str] = []
        for task in tuple(self._tasks.values()):
            if len(cancelled) == limit:
                break
            if task.state is not TaskState.QUEUED:
                continue
            if any(self._tasks[dep].state in {TaskState.DEAD, TaskState.CANCELLED}
                   for dep in task.dependencies):
                self.cancel(task.id, reason="terminal dependency failed")
                cancelled.append(task.id)
        return tuple(cancelled)

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
            _, generation, task_id = item
            task = self._tasks.get(task_id)
            if task is None or task.state is not TaskState.QUEUED or self._queued_generation.get(task_id) != generation:
                continue
            if task.attempts >= task.max_attempts:
                self._queued_generation.pop(task_id, None)
                self._transition(task, TaskState.DEAD)
                continue
            if self.dispatch_blocked(task_id) or not task.required_capabilities.issubset(worker.capabilities):
                deferred.append(item)
                continue
            updated = replace(
                task,
                state=TaskState.LEASED,
                attempts=task.attempts + 1,
                leased_to=worker_id,
                lease_deadline=self._clock() + self.default_lease_seconds,
                lease_token=uuid4().hex if self.fenced else None,
                effect_uncertain=False,
            )
            self._queued_generation.pop(task_id, None)
            self._replace(task, updated)
            worker.active.add(task_id)
            worker.accepted += 1
            leased.append(updated)
            self._event("task.leased", task_id)
        for item in deferred:
            heappush(self._queue, item)
        return leased

    def renew(self, worker_id: str, task_id: str, *, seconds: float | None = None,
              lease_token: str | None = None) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id, lease_token=lease_token)
        duration = self.default_lease_seconds if seconds is None else seconds
        if not math.isfinite(duration) or duration <= 0:
            raise LeaseError("lease renewal duration must be positive")
        updated = replace(task, lease_deadline=self._clock() + duration)
        self._replace(task, updated)
        worker.last_seen = self._clock()
        worker.renewals += 1
        self._lease_renewals += 1
        self._event("task.lease_renewed", task_id)
        return updated

    def succeed(self, worker_id: str, task_id: str, *, lease_token: str | None = None) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id, lease_token=lease_token)
        updated = replace(task, state=TaskState.SUCCEEDED, leased_to=None, lease_deadline=None,
                          lease_token=None, effect_uncertain=False)
        self._replace(task, updated)
        worker.active.discard(task_id)
        worker.completed += 1
        worker.last_seen = self._clock()
        self._event("task.succeeded", task_id)
        return updated

    def fail(self, worker_id: str, task_id: str, error: str, *,
             lease_token: str | None = None, confirmed_no_effect: bool = False) -> SwarmTask:
        task, worker = self._owned_lease(worker_id, task_id, lease_token=lease_token)
        if type(confirmed_no_effect) is not bool:
            raise LeaseError("invalid no-effect evidence declaration")
        if self.fenced and not confirmed_no_effect:
            return self._hold_uncertain(task, reason="worker outcome requires reconciliation")
        retry = task.attempts < task.max_attempts
        updated = replace(
            task,
            state=TaskState.QUEUED if retry else TaskState.DEAD,
            leased_to=None,
            lease_deadline=None,
            last_error=("confirmed-no-effect" if self.fenced else error[:2_000]),
            lease_token=None,
            effect_uncertain=False,
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

    def _hold_uncertain(self, task: SwarmTask, *, reason: str) -> SwarmTask:
        # Retain the old worker's capacity and exact attempt token. Expiration
        # alone is not evidence that a physical worker stopped or had no effect.
        updated = replace(task, state=TaskState.FAILED, last_error=reason, effect_uncertain=True)
        self._replace(task, updated)
        self._event("task.effect_uncertain", task.id)
        return updated

    def reconcile_uncertain(self, task_id: str, *, lease_token: str,
                            outcome: str, evidence_sha256: str) -> SwarmTask:
        """Trusted owner only: acknowledge an independently verified stopped effect.

        Evidence verification occurs at the existing owner boundary, not by
        accepting untrusted model/worker statements. The digest is an audit
        binding, not a signature or proof by itself.
        """
        if not self.fenced or type(evidence_sha256) is not str or len(evidence_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in evidence_sha256
        ):
            raise LeaseError("independently verified reconciliation evidence required")
        task = self._tasks.get(task_id)
        if task is None or not task.effect_uncertain or task.state is not TaskState.FAILED:
            raise LeaseError("task does not have an uncertain attempt")
        if not lease_token or task.lease_token != lease_token:
            raise LeaseError("uncertain attempt token mismatch")
        if outcome not in {"committed", "stopped-no-effect", "stopped-terminal"}:
            raise LeaseError("unsupported reconciliation outcome")
        worker = self._workers.get(task.leased_to or "")
        if worker is None or task.id not in worker.active:
            raise LeaseError("uncertain worker custody missing")
        retry = outcome == "stopped-no-effect" and task.attempts < task.max_attempts
        state = TaskState.SUCCEEDED if outcome == "committed" else (TaskState.QUEUED if retry else TaskState.DEAD)
        updated = replace(task, state=state, leased_to=None, lease_token=None, lease_deadline=None,
                          effect_uncertain=False, reconciliation_sha256=evidence_sha256,
                          last_error=None if state is TaskState.SUCCEEDED else "reconciled")
        self._replace(task, updated)
        worker.active.discard(task_id)
        if state is TaskState.SUCCEEDED:
            worker.completed += 1
        else:
            worker.failed += 1
        if retry:
            self._retries += 1
            self._requeue(task_id)
        self._event("task.reconciled." + outcome, task_id)
        return updated

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> SwarmTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise AdmissionError(f"unknown task: {task_id}")
        if task.state in {TaskState.SUCCEEDED, TaskState.CANCELLED}:
            return task
        if self.fenced and (task.state is TaskState.LEASED or task.effect_uncertain):
            raise LeaseError("stop and reconcile active or uncertain work before cancellation")
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
        if task.effect_uncertain:
            raise LeaseError("uncertain work requires reconciliation")
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
            if self.fenced:
                self._hold_uncertain(task, reason="expired attempt requires reconciliation")
                self._expired_leases += 1
                continue
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
        held = sum(task.effect_uncertain for task in self._tasks.values())
        active = snapshot.leased + held
        total_slots = snapshot.available_slots + active
        if total_slots:
            saturation = active / total_slots
        queue_pressure = snapshot.queued / max(1, snapshot.available_slots)
        status = "healthy"
        if snapshot.dead > 0 or stale or held:
            status = "degraded"
        if snapshot.workers == 0 and snapshot.queued > 0:
            status = "critical"
        return {
            "status": status,
            "stale_workers": [worker.id for worker in stale],
            "worker_saturation": round(saturation, 6),
            "queue_pressure": round(queue_pressure, 6),
            "uncertain_attempts": held,
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
            "version": (3 if any(t.wait_intent_sha256 is not None or t.singleton_scope_sha256 is not None
                                 for t in self._tasks.values()) else 2) if self.fenced else 1,
            "config": {"max_tasks": self.max_tasks, "default_lease_seconds": self.default_lease_seconds,
                       "fenced": self.fenced},
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
        fenced = config.get("fenced", False)
        version = state.get("version", 1)
        if type(fenced) is not bool or type(version) is not int or version not in (1, 2, 3) or (version >= 2) != fenced:
            raise ValueError("unsupported runtime checkpoint")
        runtime = cls(
            fenced=fenced,
            max_tasks=int(config.get("max_tasks", 100_000)),
            default_lease_seconds=float(config.get("default_lease_seconds", 30.0)),
            clock=clock,
        )
        tasks = state.get("tasks", [])
        if not isinstance(tasks, list) or len(tasks) > runtime.max_tasks:
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
                dependencies=tuple(raw.get("dependencies", ())),
                lease_token=raw.get("lease_token"),
                effect_uncertain=raw.get("effect_uncertain", False),
                reconciliation_sha256=raw.get("reconciliation_sha256"),
                wait_intent_sha256=raw.get("wait_intent_sha256"),
                wake_receipt_sha256=raw.get("wake_receipt_sha256"),
                singleton_scope_sha256=raw.get("singleton_scope_sha256"),
            )
            try:
                runtime._validate_dispatch_metadata(task, fenced=fenced, restoring=True)
            except AdmissionError as exc:
                raise ValueError("invalid dispatch metadata") from exc
            if version < 3 and any(v is not None for v in (task.wait_intent_sha256,
                    task.wake_receipt_sha256, task.singleton_scope_sha256)):
                raise ValueError("dispatch metadata requires snapshot version 3")
            if task.id in runtime._tasks or type(task.effect_uncertain) is not bool:
                raise ValueError("invalid or duplicate checkpoint task")
            if task.effect_uncertain and not fenced:
                raise ValueError("unfenced checkpoint contains uncertain execution")
            if task.reconciliation_sha256 is not None and (
                type(task.reconciliation_sha256) is not str or len(task.reconciliation_sha256) != 64
                or any(c not in "0123456789abcdef" for c in task.reconciliation_sha256)
            ):
                raise ValueError("invalid reconciliation digest")
            if fenced and (task.state is TaskState.LEASED or task.effect_uncertain):
                if not task.leased_to or type(task.lease_token) is not str or len(task.lease_token) != 32 or any(
                    char not in "0123456789abcdef" for char in task.lease_token
                ):
                    raise ValueError("missing fenced checkpoint custody")
                task = replace(task, state=TaskState.FAILED, effect_uncertain=True,
                               last_error="restored attempt requires reconciliation")
            elif task.state is TaskState.LEASED and requeue_leased:
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
                    active=set() if requeue_leased or fenced else set(raw.get("active", ())),
                    accepted=int(raw.get("accepted", 0)),
                    completed=int(raw.get("completed", 0)),
                    failed=int(raw.get("failed", 0)),
                    renewals=int(raw.get("renewals", 0)),
                    heartbeats=int(raw.get("heartbeats", 0)),
                    last_seen=float(raw.get("last_seen", clock())),
                    parent_id=raw.get("parent_id"),
                    delegated_capacity=0,
                )
                if worker.id in runtime._workers:
                    raise ValueError("duplicate checkpoint worker")
                runtime._workers[worker.id] = worker
        for worker in runtime._workers.values():
            if worker.parent_id is not None:
                if not fenced or type(worker.parent_id) is not str:
                    raise ValueError("virtual worker requires fenced custody")
                parent = runtime._workers.get(worker.parent_id)
                if parent is None or not worker.capabilities <= parent.capabilities:
                    raise ValueError("invalid virtual worker parent or capability")
                parent.delegated_capacity += worker.capacity
                try:
                    runtime.worker_lineage(worker.id)
                except LeaseError as exc:
                    raise ValueError("invalid worker hierarchy") from exc
        for worker in runtime._workers.values():
            if worker.capacity < 1 or worker.delegated_capacity + len(worker.active) > worker.capacity:
                raise ValueError("virtual worker capacity exceeded")
        from graphlib import TopologicalSorter, CycleError
        all_tasks = runtime._tasks
        for task in all_tasks.values():
            if len(task.dependencies) > 256 or len(set(task.dependencies)) != len(task.dependencies) or any(
                dep not in all_tasks for dep in task.dependencies
            ):
                raise ValueError("invalid restored dependencies")
            if task.singleton_scope_sha256 is not None and (task.state is TaskState.LEASED or task.effect_uncertain):
                if task.singleton_scope_sha256 in runtime._singleton_holders:
                    raise ValueError("duplicate restored singleton custody")
                runtime._singleton_holders[task.singleton_scope_sha256] = task.id
            if fenced and task.effect_uncertain:
                worker = runtime._workers.get(task.leased_to or "")
                if worker is None or worker.available < 1:
                    raise ValueError("invalid restored uncertain worker capacity")
                worker.active.add(task.id)
        try:
            tuple(TopologicalSorter({t.id: t.dependencies for t in all_tasks.values()}).static_order())
        except CycleError as exc:
            raise ValueError("restored dependency cycle") from exc
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

    def _owned_lease(self, worker_id: str, task_id: str, *,
                     lease_token: str | None = None) -> tuple[SwarmTask, WorkerState]:
        worker = self._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        task = self._tasks.get(task_id)
        if task is None or task.state is not TaskState.LEASED:
            raise LeaseError(f"task is not leased: {task_id}")
        if task.leased_to != worker_id:
            raise LeaseError(f"task {task_id} is leased to {task.leased_to}")
        if self.fenced:
            if not lease_token or task.lease_token != lease_token:
                raise LeaseError("attempt token mismatch")
            if task.lease_deadline is None or self._clock() >= task.lease_deadline:
                raise LeaseError("attempt expired")
        return task, worker

    def _requeue(self, task_id: str) -> None:
        task = self._tasks[task_id]
        generation = next(self._sequence)
        self._queued_generation[task_id] = generation
        heappush(self._queue, (task.priority, generation, task_id))
        # Stale entries can accumulate through cancellation/revival. Compact
        # amortized rather than turn a bounded task population into an unbounded heap.
        if len(self._queue) > max(1024, len(self._queued_generation) * 3):
            from heapq import heapify
            self._queue[:] = [item for item in self._queue
                              if self._queued_generation.get(item[2]) == item[1]
                              and self._tasks[item[2]].state is TaskState.QUEUED]
            heapify(self._queue)

    def _transition(self, task: SwarmTask, state: TaskState) -> SwarmTask:
        updated = replace(task, state=state, leased_to=None, lease_deadline=None)
        self._replace(task, updated)
        worker = self._workers.get(task.leased_to or "")
        if worker is not None:
            worker.active.discard(task.id)
        return updated

    def _replace(self, old: SwarmTask, new: SwarmTask) -> None:
        scope = new.singleton_scope_sha256
        if old.singleton_scope_sha256 != scope or old.wait_intent_sha256 != new.wait_intent_sha256:
            raise LeaseError("dispatch identity is immutable")
        if scope is not None:
            holder = self._singleton_holders.get(scope)
            if new.state is TaskState.LEASED or new.effect_uncertain:
                if holder not in (None, new.id):
                    raise LeaseError("singleton is already occupied")
                self._singleton_holders[scope] = new.id
            elif holder == old.id:
                del self._singleton_holders[scope]
        if old.state is not new.state:
            if old.state is TaskState.QUEUED:
                self._queued_generation.pop(old.id, None)
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
        for key in ("wait_intent_sha256", "wake_receipt_sha256", "singleton_scope_sha256"):
            if record[key] is None:
                del record[key]
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
            "parent_id": worker.parent_id,
        }
