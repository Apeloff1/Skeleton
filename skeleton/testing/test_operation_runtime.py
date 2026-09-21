from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream import ReplayCursor
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore


class _Reasoner:
    def __init__(self, *, fail_result: bool = False, raise_error: bool = False) -> None:
        self.calls = 0
        self.fail_result = fail_result
        self.raise_error = raise_error

    def reason(self, **kwargs):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("boom")
        if self.fail_result:
            return {"error": "no acceptable result"}
        return {"answer": "ok", "confidence": 0.9}

    def stats(self):
        return {"calls": self.calls}


def _runtime(tmp_path: Path, reasoner: _Reasoner | None = None):
    return DurableOperationRuntime(
        reasoner or _Reasoner(),
        SQLiteOperationStore(tmp_path / "operations.sqlite"),
        SQLiteOperationEventStore(tmp_path / "events.sqlite"),
        outbox_batch_size=32,
        default_deadline_s=60.0,
    )


def test_reasoning_operation_is_durable_and_streamed_to_terminal(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    result = runtime.reason("hello", tenant_id="tenant-a", actor_id="actor-a")

    operation_id = result["operation_id"]
    stored = runtime.operations.get(operation_id)
    assert stored.envelope.state is OperationState.COMPLETED
    assert stored.version == 6
    assert runtime.operations.pending_outbox(operation_id=operation_id) == ()

    events = runtime.stream.replay(ReplayCursor(operation_id))
    assert [event.type for event in events] == [
        "operation.created",
        "operation.validated",
        "operation.authorized",
        "operation.admitted",
        "operation.running",
        "operation.completed",
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5, 6]
    assert result["operation_state"] == "completed"
    assert result["operation_version"] == 6


def test_reasoning_error_result_commits_failed_terminal_state(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, _Reasoner(fail_result=True))

    result = runtime.reason("hello")

    stored = runtime.operations.get(result["operation_id"])
    assert stored.envelope.state is OperationState.FAILED
    assert runtime.stream.head(result["operation_id"])["terminal"] is True
    assert result["operation_state"] == "failed"


def test_reasoning_exception_commits_failed_state_before_reraising(tmp_path: Path) -> None:
    import pytest

    runtime = _runtime(tmp_path, _Reasoner(raise_error=True))

    with pytest.raises(RuntimeError, match="boom"):
        runtime.reason("hello")

    row = runtime.operations._connection.execute(
        "SELECT operation_id, state FROM operation_state"
    ).fetchone()
    assert row["state"] == "failed"
    assert runtime.stream.head(row["operation_id"])["terminal"] is True


def test_explicit_idempotency_key_never_reexecutes_terminal_operation(tmp_path: Path) -> None:
    reasoner = _Reasoner()
    runtime = _runtime(tmp_path, reasoner)

    first = runtime.reason(
        "hello",
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="same-request",
    )
    second = runtime.reason(
        "hello again",
        tenant_id="tenant-a",
        actor_id="actor-a",
        idempotency_key="same-request",
    )

    assert reasoner.calls == 1
    assert second == {
        "operation_id": first["operation_id"],
        "operation_state": "completed",
        "operation_version": 6,
        "idempotent_replay": True,
        "result_replay_available": False,
    }


def test_dispatch_reconciles_crash_after_stream_append_before_ack(tmp_path: Path) -> None:
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    stream = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    reasoner = _Reasoner()
    runtime = DurableOperationRuntime(reasoner, operations, stream)

    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    envelope = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="intelligence.reason",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key="idem-crash",
        trace_id="trace-crash",
    )
    operations.create(envelope, now=now)
    item = operations.pending_outbox()[0]

    stream.append(
        item.operation_id,
        item.event_type,
        item.payload,
        event_id=item.outbox_id,
        timestamp=item.created_at,
    )
    assert len(operations.pending_outbox()) == 1

    report = runtime.dispatch_outbox()

    assert report.published == 1
    assert report.remaining == 0
    assert operations.pending_outbox() == ()
    replay = stream.replay(ReplayCursor(envelope.operation_id))
    assert len(replay) == 1
    assert replay[0].event_id == item.outbox_id


def test_restart_drains_pending_transactional_outbox(tmp_path: Path) -> None:
    op_path = tmp_path / "operations.sqlite"
    stream_path = tmp_path / "events.sqlite"
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    operation_id = str(uuid4())

    with SQLiteOperationStore(op_path) as operations:
        operations.create(
            OperationEnvelope(
                operation_id=operation_id,
                tenant_id="tenant-a",
                actor_id="actor-a",
                capability="intelligence.reason",
                created_at=now,
                deadline=now + timedelta(minutes=5),
                idempotency_key="restart-idem",
                trace_id="restart-trace",
            ),
            now=now,
        )
        assert len(operations.pending_outbox()) == 1

    runtime = DurableOperationRuntime(
        _Reasoner(),
        SQLiteOperationStore(op_path),
        SQLiteOperationEventStore(stream_path),
    )
    report = runtime.dispatch_outbox()

    assert report.healthy is True
    assert report.published == 1
    assert report.remaining == 0
    assert [event.type for event in runtime.stream.replay(ReplayCursor(operation_id))] == [
        "operation.created"
    ]


def test_stats_surface_pending_outbox_and_dispatch_health(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    result = runtime.reason("hello")

    stats = runtime.stats()

    assert stats["calls"] == 1
    durable = stats["durable_operation_runtime"]
    assert durable["pending_outbox"] == 0
    assert durable["dispatch_failures"] == 0
    assert durable["last_dispatch"]["healthy"] is True
    assert result["operation_state"] == "completed"
