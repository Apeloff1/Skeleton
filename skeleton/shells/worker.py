"""Explicit queue worker for the shell execution plane.

The control plane owns admission and queueing; QueueWorker is the small,
bounded bridge that turns a claimed QueueItem into exactly one call through
ShellExecutor.

There is deliberately no background thread in this module. Callers choose when
to call run_once or a bounded drain. This keeps process ownership, shutdown,
retry policy, and queue transitions visible to Jeeves/control-plane code instead
of hiding them behind a daemon loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Any, Callable, Protocol

from skeleton.shells.queue import QueueItem, QueueState, ShellWorkQueue
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.session import ShellSession


class ExecutorLike(Protocol):
    """Structural contract consumed by QueueWorker."""

    def execute(
        self,
        command,
        *,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
        correlation_id: str | None = None,
        circuit_key: str | None = None,
    ) -> Any:
        ...


class WorkerState(str, Enum):
    CREATED = "created"
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class WorkDisposition(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    EXECUTOR_ERROR = "executor_error"
    TRANSITION_ERROR = "transition_error"


@dataclass(frozen=True)
class WorkerPolicy:
    """Bounds for an explicit worker drain."""

    max_items_per_drain: int = 100
    max_consecutive_failures: int = 10
    stop_on_executor_error: bool = False
    stop_on_transition_error: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_items_per_drain, bool) or not isinstance(self.max_items_per_drain, int):
            raise ValueError("max_items_per_drain must be an integer")
        if self.max_items_per_drain <= 0 or self.max_items_per_drain > 100_000:
            raise ValueError("max_items_per_drain outside supported bounds")
        if isinstance(self.max_consecutive_failures, bool) or not isinstance(self.max_consecutive_failures, int):
            raise ValueError("max_consecutive_failures must be an integer")
        if self.max_consecutive_failures <= 0 or self.max_consecutive_failures > 100_000:
            raise ValueError("max_consecutive_failures outside supported bounds")


@dataclass(frozen=True)
class WorkerCounters:
    claims: int = 0
    completed: int = 0
    failed: int = 0
    executor_errors: int = 0
    transition_errors: int = 0
    consecutive_failures: int = 0

    @property
    def terminal(self) -> int:
        return self.completed + self.failed


@dataclass(frozen=True)
class WorkResult:
    item_id: str
    claim_id: str
    disposition: WorkDisposition
    queue_state: QueueState
    outcome: Any | None = None
    error_type: str = ""

    @property
    def ok(self) -> bool:
        return self.disposition is WorkDisposition.COMPLETED


@dataclass(frozen=True)
class DrainReport:
    owner: str
    attempted: int
    completed: int
    failed: int
    executor_errors: int
    transition_errors: int
    stopped: bool
    queue_empty: bool
    results: tuple[WorkResult, ...]

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.executor_errors == 0 and self.transition_errors == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "attempted": self.attempted,
            "completed": self.completed,
            "failed": self.failed,
            "executor_errors": self.executor_errors,
            "transition_errors": self.transition_errors,
            "stopped": self.stopped,
            "queue_empty": self.queue_empty,
            "results": [
                {
                    "item_id": result.item_id,
                    "claim_id": result.claim_id,
                    "disposition": result.disposition.value,
                    "queue_state": result.queue_state.value,
                    "error_type": result.error_type,
                }
                for result in self.results
            ],
        }


@dataclass(frozen=True)
class WorkerSnapshot:
    owner: str
    state: WorkerState
    inflight_item_id: str | None
    stop_requested: bool
    counters: WorkerCounters

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "state": self.state.value,
            "inflight_item_id": self.inflight_item_id,
            "stop_requested": self.stop_requested,
            "counters": {
                "claims": self.counters.claims,
                "completed": self.counters.completed,
                "failed": self.counters.failed,
                "executor_errors": self.counters.executor_errors,
                "transition_errors": self.counters.transition_errors,
                "consecutive_failures": self.counters.consecutive_failures,
            },
        }


RetryFactory = Callable[[QueueItem], RetryPolicy]


def _no_retry(_item: QueueItem) -> RetryPolicy:
    return RetryPolicy.none()


class QueueWorker:
    """Claim and execute shell queue items through one ShellExecutor boundary."""

    def __init__(
        self,
        owner: str,
        queue: ShellWorkQueue,
        executor: ExecutorLike,
        *,
        session: ShellSession | None = None,
        retry_factory: RetryFactory | None = None,
        policy: WorkerPolicy | None = None,
    ) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("worker owner is required")
        if len(owner) > 256:
            raise ValueError("worker owner is too long")
        self.owner = owner
        self.queue = queue
        self.executor = executor
        self.session = session
        self.retry_factory = retry_factory or _no_retry
        self.policy = policy or WorkerPolicy()
        self._state = WorkerState.CREATED
        self._inflight_item_id: str | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._counters = WorkerCounters()

    def _set_state(self, state: WorkerState, *, inflight: str | None = None) -> None:
        with self._lock:
            self._state = state
            self._inflight_item_id = inflight

    def _replace_counters(self, **changes: int) -> None:
        values = {
            "claims": self._counters.claims,
            "completed": self._counters.completed,
            "failed": self._counters.failed,
            "executor_errors": self._counters.executor_errors,
            "transition_errors": self._counters.transition_errors,
            "consecutive_failures": self._counters.consecutive_failures,
        }
        values.update(changes)
        self._counters = WorkerCounters(**values)

    def _record_claim(self) -> None:
        with self._lock:
            self._replace_counters(claims=self._counters.claims + 1)

    def _record_success(self) -> None:
        with self._lock:
            self._replace_counters(
                completed=self._counters.completed + 1,
                consecutive_failures=0,
            )

    def _record_failure(self, disposition: WorkDisposition) -> None:
        with self._lock:
            changes = {
                "failed": self._counters.failed + 1,
                "consecutive_failures": self._counters.consecutive_failures + 1,
            }
            if disposition is WorkDisposition.EXECUTOR_ERROR:
                changes["executor_errors"] = self._counters.executor_errors + 1
            elif disposition is WorkDisposition.TRANSITION_ERROR:
                changes["transition_errors"] = self._counters.transition_errors + 1
            self._replace_counters(**changes)
            if self._counters.consecutive_failures >= self.policy.max_consecutive_failures:
                self._stop.set()
                self._state = WorkerState.FAILED

    def snapshot(self) -> WorkerSnapshot:
        with self._lock:
            return WorkerSnapshot(
                owner=self.owner,
                state=self._state,
                inflight_item_id=self._inflight_item_id,
                stop_requested=self._stop.is_set(),
                counters=self._counters,
            )

    def request_stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._state not in {WorkerState.STOPPED, WorkerState.FAILED}:
                self._state = WorkerState.STOPPING

    def reset_stop(self) -> None:
        """Clear a requested stop when no item is in flight."""

        with self._lock:
            if self._inflight_item_id is not None:
                raise RuntimeError("cannot reset stop while work is in flight")
            if self._state is WorkerState.FAILED:
                raise RuntimeError("failed workers cannot be reset")
            self._stop.clear()
            self._state = WorkerState.IDLE

    def _correlation_id(self, item: QueueItem) -> str:
        claim = item.claim_id or "unclaimed"
        return f"shellq:{item.item_id}:{claim}"

    def _transition_failed(self, item: QueueItem) -> QueueItem:
        try:
            return self.queue.fail(item)
        except RuntimeError:
            self._record_failure(WorkDisposition.TRANSITION_ERROR)
            if self.policy.stop_on_transition_error:
                self._stop.set()
                self._set_state(WorkerState.FAILED)
            raise

    def run_once(self) -> WorkResult | None:
        """Claim at most one item and execute it.

        Every successful claim has one cleanup owner: this method.  Once an
        item becomes inflight, the inflight marker is cleared on every exit,
        including retry-factory failures, executor failures, stale queue
        transitions, and raised policy errors.
        """

        if self._stop.is_set():
            if self.snapshot().state is not WorkerState.FAILED:
                self._set_state(WorkerState.STOPPED)
            return None

        item = self.queue.claim(self.owner)
        if item is None:
            self._set_state(WorkerState.IDLE)
            return None

        self._record_claim()
        self._set_state(WorkerState.RUNNING, inflight=item.item_id)

        try:
            try:
                retry = self.retry_factory(item)
            except Exception:
                # A retry factory is control-plane code.  Once it has accepted
                # a claimed item, failure to produce policy must not strand
                # that claim in CLAIMED state.
                self._transition_failed(item)
                self._record_failure(WorkDisposition.EXECUTOR_ERROR)
                self._stop.set()
                self._set_state(WorkerState.FAILED, inflight=item.item_id)
                raise

            if not isinstance(retry, RetryPolicy):
                self._transition_failed(item)
                self._record_failure(WorkDisposition.EXECUTOR_ERROR)
                self._stop.set()
                self._set_state(WorkerState.FAILED, inflight=item.item_id)
                raise TypeError("retry_factory must return RetryPolicy")

            try:
                outcome = self.executor.execute(
                    item.command,
                    retry=retry,
                    session=self.session,
                    correlation_id=self._correlation_id(item),
                    circuit_key=item.command.command,
                )
            except Exception as exc:
                # First prove ownership can make the claimed item terminal. If
                # that transition is stale, _transition_failed records the
                # stronger transition failure and raises. The outer finally
                # still clears the inflight marker.
                terminal = self._transition_failed(item)
                self._record_failure(WorkDisposition.EXECUTOR_ERROR)
                if self.policy.stop_on_executor_error:
                    self._stop.set()
                    self._set_state(WorkerState.FAILED, inflight=item.item_id)
                elif self.snapshot().state is not WorkerState.FAILED:
                    self._set_state(WorkerState.IDLE, inflight=item.item_id)
                return WorkResult(
                    item_id=item.item_id,
                    claim_id=item.claim_id or "",
                    disposition=WorkDisposition.EXECUTOR_ERROR,
                    queue_state=terminal.state,
                    outcome=None,
                    error_type=type(exc).__name__,
                )

            try:
                if bool(getattr(outcome, "ok", False)):
                    terminal = self.queue.complete(item)
                    self._record_success()
                    disposition = WorkDisposition.COMPLETED
                else:
                    terminal = self.queue.fail(item)
                    self._record_failure(WorkDisposition.FAILED)
                    disposition = WorkDisposition.FAILED
            except RuntimeError:
                self._record_failure(WorkDisposition.TRANSITION_ERROR)
                self._stop.set()
                self._set_state(WorkerState.FAILED, inflight=item.item_id)
                raise

            snapshot = self.snapshot()
            if self._stop.is_set() and snapshot.state is not WorkerState.FAILED:
                self._set_state(WorkerState.STOPPING, inflight=item.item_id)
            elif not self._stop.is_set():
                self._set_state(WorkerState.IDLE, inflight=item.item_id)

            return WorkResult(
                item_id=item.item_id,
                claim_id=item.claim_id or "",
                disposition=disposition,
                queue_state=terminal.state,
                outcome=outcome,
            )
        finally:
            with self._lock:
                self._inflight_item_id = None

    def drain(self, *, max_items: int | None = None) -> DrainReport:
        """Process a bounded number of available items and return evidence."""

        requested = self.policy.max_items_per_drain if max_items is None else max_items
        if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
            raise ValueError("max_items must be a positive integer")
        limit = min(requested, self.policy.max_items_per_drain)
        results: list[WorkResult] = []
        queue_empty = False

        for _ in range(limit):
            if self._stop.is_set():
                break
            result = self.run_once()
            if result is None:
                queue_empty = not self._stop.is_set()
                break
            results.append(result)

        if self._stop.is_set() and self.snapshot().state is not WorkerState.FAILED:
            self._set_state(WorkerState.STOPPED)

        return DrainReport(
            owner=self.owner,
            attempted=len(results),
            completed=sum(result.disposition is WorkDisposition.COMPLETED for result in results),
            failed=sum(result.disposition is WorkDisposition.FAILED for result in results),
            executor_errors=sum(result.disposition is WorkDisposition.EXECUTOR_ERROR for result in results),
            transition_errors=sum(result.disposition is WorkDisposition.TRANSITION_ERROR for result in results),
            stopped=self._stop.is_set(),
            queue_empty=queue_empty,
            results=tuple(results),
        )


@dataclass(frozen=True)
class WorkerGroupSnapshot:
    workers: tuple[WorkerSnapshot, ...]

    @property
    def running(self) -> int:
        return sum(snapshot.state is WorkerState.RUNNING for snapshot in self.workers)

    @property
    def failed(self) -> int:
        return sum(snapshot.state is WorkerState.FAILED for snapshot in self.workers)

    def to_dict(self) -> dict[str, object]:
        return {
            "running": self.running,
            "failed": self.failed,
            "workers": [snapshot.to_dict() for snapshot in self.workers],
        }


class WorkerGroup:
    """Deterministic collection of workers sharing one queue."""

    def __init__(self, workers: tuple[QueueWorker, ...]) -> None:
        if not workers:
            raise ValueError("at least one worker is required")
        owners = [worker.owner for worker in workers]
        if len(set(owners)) != len(owners):
            raise ValueError("worker owners must be unique")
        queues = {id(worker.queue) for worker in workers}
        if len(queues) != 1:
            raise ValueError("worker group members must share one queue")
        self.workers = tuple(workers)

    def snapshot(self) -> WorkerGroupSnapshot:
        return WorkerGroupSnapshot(tuple(worker.snapshot() for worker in self.workers))

    def request_stop(self) -> None:
        for worker in self.workers:
            worker.request_stop()

    def drain_round_robin(self, *, max_rounds: int = 1) -> tuple[WorkResult, ...]:
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds <= 0:
            raise ValueError("max_rounds must be a positive integer")
        results: list[WorkResult] = []
        for _ in range(max_rounds):
            progressed = False
            for worker in self.workers:
                if worker.snapshot().stop_requested:
                    continue
                result = worker.run_once()
                if result is not None:
                    progressed = True
                    results.append(result)
            if not progressed:
                break
        return tuple(results)
