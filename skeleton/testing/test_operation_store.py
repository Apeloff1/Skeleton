from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from skeleton.contracts.operation import (
    OperationEnvelope,
    OperationState,
    OperationTransitionError,
)
from skeleton.frontier.operation_stream import ReplayCursor
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import (
    OperationStoreConflict,
    OperationStoreCorruptionError,
    SQLiteOperationStore,
)


BASE_TIME = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _operation(
    *,
    operation_id: str | None = None,
    idempotency_key: str = "idem-1",
    trace_id: str = "trace-1",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=operation_id or str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key=idempotency_key,
        trace_id=trace_id,
    )


def test_operation_store_persists_state_and_version_across_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operations.sqlite"
    operation = _operation()

    with SQLiteOperationStore(path) as store:
        created = store.create(operation, now=BASE_TIME)
        validated = store.transition(
            operation.operation_id,
            OperationState.VALIDATED,
            expected_version=created.version,
            now=BASE_TIME + timedelta(seconds=1),
        )
        assert validated.version == 2
        assert validated.envelope.state is OperationState.VALIDATED

    with SQLiteOperationStore(path) as store:
        restored = store.get(operation.operation_id)
        assert restored.version == 2
        assert restored.envelope.state is OperationState.VALIDATED
        assert restored.envelope.identity_digest == operation.identity_digest


def test_duplicate_idempotency_identity_returns_original_operation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operations.sqlite"
    first = _operation(operation_id=str(uuid4()), trace_id="trace-first")
    retry = _operation(operation_id=str(uuid4()), trace_id="trace-retry")

    with SQLiteOperationStore(path) as store:
        original = store.create(first, now=BASE_TIME)
        resolved = store.create(
            retry,
            now=BASE_TIME + timedelta(seconds=1),
        )

    assert original.envelope.operation_id == first.operation_id
    assert resolved.envelope.operation_id == first.operation_id
    assert resolved.envelope.trace_id == "trace-first"
    assert resolved.version == 1


def test_same_operation_id_with_different_identity_fails_closed(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    first = _operation(operation_id=operation_id, idempotency_key="idem-a")
    conflict = _operation(operation_id=operation_id, idempotency_key="idem-b")

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        store.create(first, now=BASE_TIME)
        with pytest.raises(
            OperationStoreConflict,
            match="different content",
        ):
            store.create(conflict, now=BASE_TIME + timedelta(seconds=1))


def test_illegal_transition_rolls_back_state_and_outbox(
    tmp_path: Path,
) -> None:
    operation = _operation()

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        store.create(operation, now=BASE_TIME)
        before = store.pending_outbox()

        with pytest.raises(OperationTransitionError):
            store.transition(
                operation.operation_id,
                OperationState.RUNNING,
                now=BASE_TIME + timedelta(seconds=1),
            )

        after = store.get(operation.operation_id)
        assert after.version == 1
        assert after.envelope.state is OperationState.CREATED
        assert store.pending_outbox() == before


def test_optimistic_version_guard_rejects_stale_transition(
    tmp_path: Path,
) -> None:
    operation = _operation()

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        created = store.create(operation, now=BASE_TIME)
        store.transition(
            operation.operation_id,
            OperationState.VALIDATED,
            expected_version=created.version,
            now=BASE_TIME + timedelta(seconds=1),
        )

        with pytest.raises(OperationStoreConflict, match="version changed"):
            store.transition(
                operation.operation_id,
                OperationState.AUTHORIZED,
                expected_version=created.version,
                now=BASE_TIME + timedelta(seconds=2),
            )


def test_terminal_state_is_durable_and_cannot_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operations.sqlite"
    operation = _operation()

    with SQLiteOperationStore(path) as store:
        current = store.create(operation, now=BASE_TIME)
        for index, state in enumerate(
            (
                OperationState.VALIDATED,
                OperationState.AUTHORIZED,
                OperationState.ADMITTED,
                OperationState.RUNNING,
                OperationState.COMPLETED,
            ),
            start=1,
        ):
            current = store.transition(
                operation.operation_id,
                state,
                expected_version=current.version,
                now=BASE_TIME + timedelta(seconds=index),
            )
        assert current.terminal is True

    with SQLiteOperationStore(path) as store:
        restored = store.get(operation.operation_id)
        assert restored.envelope.state is OperationState.COMPLETED
        with pytest.raises(OperationTransitionError):
            store.transition(
                operation.operation_id,
                OperationState.RUNNING,
                expected_version=restored.version,
                now=BASE_TIME + timedelta(seconds=10),
            )


def test_state_transition_and_outbox_intent_commit_together(
    tmp_path: Path,
) -> None:
    operation = _operation()

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        created = store.create(operation, now=BASE_TIME)
        validated = store.transition(
            operation.operation_id,
            OperationState.VALIDATED,
            expected_version=created.version,
            now=BASE_TIME + timedelta(seconds=1),
        )
        events = store.pending_outbox()

        assert validated.version == 2
        assert [event.operation_version for event in events] == [1, 2]
        assert [event.event_type for event in events] == [
            "operation.created",
            "operation.validated",
        ]
        assert events[1].payload == {
            "state": "validated",
            "trace_id": operation.trace_id,
            "version": 2,
        }
        UUID(events[0].outbox_id)
        UUID(events[1].outbox_id)


def test_outbox_dispatch_to_stream_is_retry_stable_and_acknowledgeable(
    tmp_path: Path,
) -> None:
    operation = _operation()
    operation_path = tmp_path / "operations.sqlite"
    stream_path = tmp_path / "events.sqlite"

    with SQLiteOperationStore(operation_path) as operations:
        created = operations.create(operation, now=BASE_TIME)
        operations.transition(
            operation.operation_id,
            OperationState.VALIDATED,
            expected_version=created.version,
            now=BASE_TIME + timedelta(seconds=1),
        )
        pending = operations.pending_outbox()

        with SQLiteOperationEventStore(stream_path) as stream:
            delivered = []
            for sequence, item in enumerate(pending, start=1):
                event = item.as_stream_event(sequence)
                delivered.append(stream.append_event(event))
                # Retrying the exact outbox event is idempotent.
                assert stream.append_event(event).event_id == item.outbox_id
                receipt = operations.acknowledge_outbox(
                    item.outbox_id,
                    published_at=BASE_TIME + timedelta(seconds=10 + sequence),
                )
                assert receipt.published is True

            assert [event.type for event in delivered] == [
                "operation.created",
                "operation.validated",
            ]
            assert [event.sequence for event in stream.replay(
                ReplayCursor(operation.operation_id)
            )] == [1, 2]

        assert operations.pending_outbox() == ()


def test_outbox_acknowledgement_is_idempotent(
    tmp_path: Path,
) -> None:
    operation = _operation()

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        store.create(operation, now=BASE_TIME)
        event = store.pending_outbox()[0]
        first = store.acknowledge_outbox(
            event.outbox_id,
            published_at=BASE_TIME + timedelta(seconds=1),
        )
        second = store.acknowledge_outbox(
            event.outbox_id,
            published_at=BASE_TIME + timedelta(seconds=2),
        )

        assert first == second
        assert first.published_at == BASE_TIME + timedelta(seconds=1)


def test_persisted_operation_corruption_is_rejected(
    tmp_path: Path,
) -> None:
    operation = _operation()

    with SQLiteOperationStore(tmp_path / "operations.sqlite") as store:
        store.create(operation, now=BASE_TIME)
        store._connection.execute(
            """
            UPDATE operation_state
            SET state = 'not-a-state'
            WHERE namespace = ? AND operation_id = ?
            """,
            (store.namespace, operation.operation_id),
        )

        with pytest.raises(OperationStoreCorruptionError):
            store.get(operation.operation_id)
