from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.frontier.operation_stream import (
    OperationEventLog,
    ReplayCursor,
    StreamBackpressureError,
    StreamContractError,
    StreamDuplicateConflictError,
    StreamEvent,
    StreamReplayGapError,
    StreamTerminalError,
)


def test_stream_assigns_monotonic_sequence_and_replays_after_cursor() -> None:
    operation_id = str(uuid4())
    log = OperationEventLog(operation_id)

    first = log.append("operation.started", {"stage": "routing"})
    second = log.append("operation.progress", {"stage": "provider"})

    assert first.sequence == 1
    assert second.sequence == 2
    replay = log.replay(ReplayCursor(operation_id, after_sequence=1))
    assert replay == (second,)


def test_stream_terminal_event_prevents_future_writes() -> None:
    log = OperationEventLog(str(uuid4()))
    log.append("operation.completed", {"ok": True})

    assert log.terminal is True
    with pytest.raises(StreamTerminalError):
        log.append("operation.progress", {"late": True})


def test_stream_backpressures_instead_of_dropping() -> None:
    operation_id = str(uuid4())
    log = OperationEventLog(operation_id, capacity=2)
    log.append("operation.started", {})
    log.append("operation.progress", {"n": 1})

    with pytest.raises(StreamBackpressureError):
        log.append("operation.progress", {"n": 2})

    assert log.compact_through(1) == 1
    event = log.append("operation.progress", {"n": 2})
    assert event.sequence == 3

    with pytest.raises(StreamReplayGapError):
        log.replay(ReplayCursor(operation_id, after_sequence=0))


def test_stream_rejects_out_of_order_prebuilt_event() -> None:
    operation_id = str(uuid4())
    log = OperationEventLog(operation_id)
    event = StreamEvent(
        operation_id=operation_id,
        event_id=str(uuid4()),
        sequence=2,
        type="operation.progress",
        timestamp=datetime.now(timezone.utc),
        payload={},
    )

    with pytest.raises(StreamContractError, match="out-of-order"):
        log.append_event(event)


def test_stream_duplicate_event_id_is_idempotent_only_for_identical_event() -> None:
    operation_id = str(uuid4())
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    event = StreamEvent(
        operation_id=operation_id,
        event_id=event_id,
        sequence=1,
        type="operation.started",
        timestamp=timestamp,
        payload={"x": 1},
    )
    log = OperationEventLog(operation_id)
    assert log.append_event(event) is event
    assert log.append_event(event) is event

    conflicting = StreamEvent(
        operation_id=operation_id,
        event_id=event_id,
        sequence=2,
        type="operation.progress",
        timestamp=timestamp,
        payload={"x": 2},
    )
    with pytest.raises(StreamDuplicateConflictError):
        log.append_event(conflicting)


def test_stream_payload_must_be_strict_json() -> None:
    with pytest.raises(StreamContractError, match="strict JSON"):
        StreamEvent(
            operation_id=str(uuid4()),
            event_id=str(uuid4()),
            sequence=1,
            type="operation.progress",
            timestamp=datetime.now(timezone.utc),
            payload={"bad": float("nan")},
        )
