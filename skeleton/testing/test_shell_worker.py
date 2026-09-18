"""Regression tests for explicit shell queue workers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.shells.queue import QueueState, ShellWorkQueue
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker import (
    QueueWorker,
    WorkDisposition,
    WorkerGroup,
    WorkerPolicy,
    WorkerState,
)


@dataclass(frozen=True)
class FakeOutcome:
    ok: bool


class FakeExecutor:
    def __init__(self, outcomes=()) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def execute(
        self,
        command,
        *,
        retry=None,
        session=None,
        correlation_id=None,
        circuit_key=None,
    ):
        self.calls.append(
            {
                "command": command,
                "retry": retry,
                "session": session,
                "correlation_id": correlation_id,
                "circuit_key": circuit_key,
            }
        )
        if not self.outcomes:
            return FakeOutcome(True)
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _command(name: str = "python") -> ShellCommand:
    return ShellCommand(name, ("-c", "print('ok')"))


def test_worker_requires_owner() -> None:
    with pytest.raises(ValueError):
        QueueWorker("", ShellWorkQueue(), FakeExecutor())


@pytest.mark.parametrize("value", [0, -1, True, 100_001])
def test_worker_policy_rejects_bad_drain_bound(value: object) -> None:
    with pytest.raises(ValueError):
        WorkerPolicy(max_items_per_drain=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True, 100_001])
def test_worker_policy_rejects_bad_failure_bound(value: object) -> None:
    with pytest.raises(ValueError):
        WorkerPolicy(max_consecutive_failures=value)  # type: ignore[arg-type]


def test_empty_run_once_is_idle() -> None:
    worker = QueueWorker("worker-a", ShellWorkQueue(), FakeExecutor())
    assert worker.run_once() is None
    snap = worker.snapshot()
    assert snap.state is WorkerState.IDLE
    assert snap.counters.claims == 0


def test_success_claims_executes_and_completes() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="job-1")
    executor = FakeExecutor([FakeOutcome(True)])
    worker = QueueWorker("worker-a", queue, executor)

    result = worker.run_once()

    assert result is not None
    assert result.item_id == item.item_id
    assert result.disposition is WorkDisposition.COMPLETED
    assert result.queue_state is QueueState.COMPLETED
    assert queue.get(item.item_id).state is QueueState.COMPLETED
    assert worker.snapshot().counters.completed == 1
    assert worker.snapshot().counters.consecutive_failures == 0
    assert executor.calls[0]["circuit_key"] == "python"
    assert str(executor.calls[0]["correlation_id"]).startswith("shellq:job-1:")


def test_non_ok_outcome_fails_queue_item() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="job-2")
    worker = QueueWorker("worker-a", queue, FakeExecutor([FakeOutcome(False)]))

    result = worker.run_once()

    assert result is not None
    assert result.disposition is WorkDisposition.FAILED
    assert result.queue_state is QueueState.FAILED
    assert queue.get(item.item_id).state is QueueState.FAILED
    snap = worker.snapshot()
    assert snap.counters.failed == 1
    assert snap.counters.executor_errors == 0
    assert snap.counters.consecutive_failures == 1
    assert snap.state is WorkerState.IDLE


def test_executor_exception_becomes_terminal_failed_item() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="job-3")
    worker = QueueWorker("worker-a", queue, FakeExecutor([RuntimeError("boom")]))

    result = worker.run_once()

    assert result is not None
    assert result.disposition is WorkDisposition.EXECUTOR_ERROR
    assert result.error_type == "RuntimeError"
    assert queue.get(item.item_id).state is QueueState.FAILED
    snap = worker.snapshot()
    assert snap.counters.failed == 1
    assert snap.counters.executor_errors == 1
    assert snap.state is WorkerState.IDLE


def test_executor_error_can_stop_worker() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command())
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor([RuntimeError("boom")]),
        policy=WorkerPolicy(stop_on_executor_error=True),
    )

    result = worker.run_once()

    assert result is not None
    assert result.disposition is WorkDisposition.EXECUTOR_ERROR
    snap = worker.snapshot()
    assert snap.stop_requested is True
    assert snap.state is WorkerState.FAILED
    assert worker.run_once() is None
    assert worker.snapshot().state is WorkerState.STOPPED


def test_consecutive_failure_guard_trips() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command(), item_id="a")
    queue.enqueue(_command(), item_id="b")
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor([FakeOutcome(False), FakeOutcome(False)]),
        policy=WorkerPolicy(max_consecutive_failures=2),
    )

    first = worker.run_once()
    second = worker.run_once()

    assert first is not None and first.disposition is WorkDisposition.FAILED
    assert second is not None and second.disposition is WorkDisposition.FAILED
    snap = worker.snapshot()
    assert snap.counters.consecutive_failures == 2
    assert snap.stop_requested is True
    assert snap.state is WorkerState.FAILED


def test_success_resets_consecutive_failure_counter() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command(), item_id="a")
    queue.enqueue(_command(), item_id="b")
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor([FakeOutcome(False), FakeOutcome(True)]),
    )

    worker.run_once()
    assert worker.snapshot().counters.consecutive_failures == 1
    worker.run_once()
    assert worker.snapshot().counters.consecutive_failures == 0


def test_retry_factory_is_passed_to_executor() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command(), item_id="retry")
    retry = RetryPolicy.transient_codes({75}, max_attempts=4)
    seen: list[str] = []

    def factory(item):
        seen.append(item.item_id)
        return retry

    executor = FakeExecutor([FakeOutcome(True)])
    worker = QueueWorker("worker-a", queue, executor, retry_factory=factory)
    worker.run_once()

    assert seen == ["retry"]
    assert executor.calls[0]["retry"] is retry


def test_invalid_retry_factory_fails_claim_and_raises() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="bad-retry")
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor(),
        retry_factory=lambda _item: object(),  # type: ignore[return-value]
    )

    with pytest.raises(TypeError):
        worker.run_once()

    assert queue.get(item.item_id).state is QueueState.FAILED


def test_session_is_forwarded_without_worker_mutation() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command())
    sentinel = object()
    executor = FakeExecutor([FakeOutcome(True)])
    worker = QueueWorker("worker-a", queue, executor, session=sentinel)  # type: ignore[arg-type]

    worker.run_once()

    assert executor.calls[0]["session"] is sentinel


def test_request_stop_prevents_new_claim() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="later")
    executor = FakeExecutor()
    worker = QueueWorker("worker-a", queue, executor)

    worker.request_stop()

    assert worker.run_once() is None
    assert queue.get(item.item_id).state is QueueState.QUEUED
    assert executor.calls == []
    assert worker.snapshot().state is WorkerState.STOPPED


def test_reset_stop_allows_future_claim() -> None:
    queue = ShellWorkQueue()
    item = queue.enqueue(_command(), item_id="resume")
    worker = QueueWorker("worker-a", queue, FakeExecutor([FakeOutcome(True)]))

    worker.request_stop()
    worker.reset_stop()
    result = worker.run_once()

    assert result is not None and result.ok
    assert queue.get(item.item_id).state is QueueState.COMPLETED


def test_failed_worker_cannot_reset_stop() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command())
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor([FakeOutcome(False)]),
        policy=WorkerPolicy(max_consecutive_failures=1),
    )
    worker.run_once()

    with pytest.raises(RuntimeError):
        worker.reset_stop()


def test_drain_stops_when_queue_is_empty() -> None:
    queue = ShellWorkQueue()
    for index in range(3):
        queue.enqueue(_command(), item_id=f"job-{index}")
    worker = QueueWorker("worker-a", queue, FakeExecutor())

    report = worker.drain()

    assert report.attempted == 3
    assert report.completed == 3
    assert report.failed == 0
    assert report.queue_empty is True
    assert report.ok is True


def test_drain_honors_explicit_limit() -> None:
    queue = ShellWorkQueue()
    for index in range(5):
        queue.enqueue(_command(), item_id=f"job-{index}")
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor(),
        policy=WorkerPolicy(max_items_per_drain=5),
    )

    report = worker.drain(max_items=2)

    assert report.attempted == 2
    assert queue.counts()["queued"] == 3


def test_drain_never_exceeds_worker_policy_limit() -> None:
    queue = ShellWorkQueue()
    for index in range(5):
        queue.enqueue(_command(), item_id=f"job-{index}")
    worker = QueueWorker(
        "worker-a",
        queue,
        FakeExecutor(),
        policy=WorkerPolicy(max_items_per_drain=2),
    )

    report = worker.drain(max_items=999)

    assert report.attempted == 2
    assert queue.counts()["queued"] == 3


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_drain_rejects_invalid_limit(value: object) -> None:
    worker = QueueWorker("worker-a", ShellWorkQueue(), FakeExecutor())
    with pytest.raises(ValueError):
        worker.drain(max_items=value)  # type: ignore[arg-type]


def test_drain_report_is_secret_minimized() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(
        ShellCommand(
            "python",
            ("--token=super-secret",),
            env={"API_TOKEN": "super-secret"},
        ),
        item_id="secret-job",
    )
    worker = QueueWorker("worker-a", queue, FakeExecutor([RuntimeError("contains super-secret")]))

    report = worker.drain()
    payload = str(report.to_dict())

    assert "super-secret" not in payload
    assert "API_TOKEN" not in payload
    assert "--token" not in payload


def test_queue_priority_is_preserved_by_worker() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(ShellCommand("python", ("low",)), priority=200, item_id="low")
    queue.enqueue(ShellCommand("python", ("high",)), priority=1, item_id="high")
    executor = FakeExecutor()
    worker = QueueWorker("worker-a", queue, executor)

    worker.run_once()

    assert queue.get("high").state is QueueState.COMPLETED
    assert queue.get("low").state is QueueState.QUEUED


def test_worker_snapshot_is_stable_shape() -> None:
    worker = QueueWorker("worker-a", ShellWorkQueue(), FakeExecutor())
    payload = worker.snapshot().to_dict()

    assert payload["owner"] == "worker-a"
    assert payload["state"] == "created"
    assert payload["inflight_item_id"] is None
    assert payload["stop_requested"] is False
    assert payload["counters"]["claims"] == 0


def test_group_requires_at_least_one_worker() -> None:
    with pytest.raises(ValueError):
        WorkerGroup(())


def test_group_rejects_duplicate_owner_names() -> None:
    queue = ShellWorkQueue()
    workers = (
        QueueWorker("same", queue, FakeExecutor()),
        QueueWorker("same", queue, FakeExecutor()),
    )
    with pytest.raises(ValueError):
        WorkerGroup(workers)


def test_group_requires_shared_queue() -> None:
    workers = (
        QueueWorker("a", ShellWorkQueue(), FakeExecutor()),
        QueueWorker("b", ShellWorkQueue(), FakeExecutor()),
    )
    with pytest.raises(ValueError):
        WorkerGroup(workers)


def test_round_robin_gives_each_worker_one_claim_per_round() -> None:
    queue = ShellWorkQueue()
    for index in range(4):
        queue.enqueue(_command(), item_id=f"job-{index}")
    first_executor = FakeExecutor()
    second_executor = FakeExecutor()
    group = WorkerGroup(
        (
            QueueWorker("a", queue, first_executor),
            QueueWorker("b", queue, second_executor),
        )
    )

    results = group.drain_round_robin(max_rounds=1)

    assert len(results) == 2
    assert queue.counts()["completed"] == 2
    assert queue.counts()["queued"] == 2
    assert len(first_executor.calls) == 1
    assert len(second_executor.calls) == 1


def test_round_robin_stops_after_empty_round() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command(), item_id="only")
    group = WorkerGroup(
        (
            QueueWorker("a", queue, FakeExecutor()),
            QueueWorker("b", queue, FakeExecutor()),
        )
    )

    results = group.drain_round_robin(max_rounds=100)

    assert len(results) == 1
    assert queue.counts()["completed"] == 1


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_group_rejects_invalid_round_limit(value: object) -> None:
    queue = ShellWorkQueue()
    group = WorkerGroup((QueueWorker("a", queue, FakeExecutor()),))
    with pytest.raises(ValueError):
        group.drain_round_robin(max_rounds=value)  # type: ignore[arg-type]


def test_group_stop_is_broadcast() -> None:
    queue = ShellWorkQueue()
    group = WorkerGroup(
        (
            QueueWorker("a", queue, FakeExecutor()),
            QueueWorker("b", queue, FakeExecutor()),
        )
    )

    group.request_stop()
    snapshot = group.snapshot()

    assert all(worker.stop_requested for worker in snapshot.workers)
    assert snapshot.running == 0


def test_group_snapshot_reports_failed_worker() -> None:
    queue = ShellWorkQueue()
    queue.enqueue(_command())
    failed = QueueWorker(
        "a",
        queue,
        FakeExecutor([FakeOutcome(False)]),
        policy=WorkerPolicy(max_consecutive_failures=1),
    )
    healthy = QueueWorker("b", queue, FakeExecutor())
    group = WorkerGroup((failed, healthy))

    failed.run_once()
    snapshot = group.snapshot()

    assert snapshot.failed == 1
    assert snapshot.to_dict()["failed"] == 1
