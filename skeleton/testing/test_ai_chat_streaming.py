from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.assistant.streaming import (
    ChatStreamError,
    TurnStreamCursor,
    project_turn_event,
    project_turn_page,
    require_resume_cursor,
)
from skeleton.ai.assistant.turn_runtime import (
    FailureClass,
    TurnState,
    make_event,
    start_turn,
)


NOW = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)
OPERATION = "operation-stream-1"
REQUEST_DIGEST = "a" * 64


def _journal():
    snapshot = start_turn(
        operation_id=OPERATION,
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="user-1",
    )
    events = []
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.VERIFYING,
            TurnState.FINALIZING,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            TurnState.COMPLETE,
        ),
        start=1,
    ):
        event = make_event(
            snapshot,
            state,
            observed_at=NOW + timedelta(seconds=offset),
            payload={
                "secret_prompt": "must never reach stream projection",
                "internal_score": 0.91,
            },
        )
        snapshot = snapshot.apply(event)
        events.append(event)
    return tuple(events)


def test_projection_is_content_minimized_and_deterministic() -> None:
    event = _journal()[0]
    public = project_turn_event(event)
    payload = public.as_dict()

    assert public.kind == "turn.accepted"
    assert public.sequence == 1
    assert len(public.event_id) == 64
    assert public.event_digest == event.digest
    assert "payload" not in payload
    assert "secret_prompt" not in repr(payload)
    assert project_turn_event(event) == public


def test_reconnect_page_advances_exact_cursor() -> None:
    events = _journal()
    initial = TurnStreamCursor(operation_id=OPERATION)
    first = project_turn_page(events, cursor=initial, limit=4)

    assert [event.sequence for event in first.events] == [1, 2, 3, 4]
    assert first.cursor.last_seen_sequence == 4
    assert first.cursor.last_event_digest == events[3].digest
    assert first.terminal is False

    second = project_turn_page(events, cursor=first.cursor, limit=100)
    assert [event.sequence for event in second.events] == [5, 6, 7, 8, 9]
    assert second.cursor.last_seen_sequence == 9
    assert second.terminal is True
    assert second.events[-1].kind == "turn.completed"
    assert len(second.digest) == 64


def test_overlapping_repository_page_does_not_duplicate_prior_events() -> None:
    events = _journal()
    cursor = TurnStreamCursor(
        operation_id=OPERATION,
        last_seen_sequence=3,
        last_event_digest=events[2].digest,
    )
    page = project_turn_page(events[1:], cursor=cursor)
    assert [event.sequence for event in page.events] == list(range(4, 10))


def test_sequence_gap_fails_closed() -> None:
    events = _journal()
    with pytest.raises(ChatStreamError, match="sequence gap"):
        project_turn_page(
            (events[0], events[2]),
            cursor=TurnStreamCursor(operation_id=OPERATION),
        )


def test_digest_chain_mismatch_fails_closed() -> None:
    events = _journal()
    wrong = TurnStreamCursor(
        operation_id=OPERATION,
        last_seen_sequence=1,
        last_event_digest="b" * 64,
    )
    with pytest.raises(ChatStreamError, match="digest chain"):
        project_turn_page(events[1:], cursor=wrong)


def test_cross_operation_event_fails_closed() -> None:
    events = _journal()
    other = start_turn(
        operation_id="other-operation",
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="user-1",
    )
    event = make_event(
        other,
        TurnState.ADMITTED,
        observed_at=NOW,
    )
    with pytest.raises(ChatStreamError, match="different operation"):
        project_turn_page(
            (event,),
            cursor=TurnStreamCursor(operation_id=OPERATION),
        )


def test_resume_cursor_requires_digest_after_sequence_zero() -> None:
    assert require_resume_cursor(
        operation_id=OPERATION,
        last_seen_sequence=0,
        last_event_digest=None,
    ).last_seen_sequence == 0

    with pytest.raises(ChatStreamError, match="requires event digest"):
        require_resume_cursor(
            operation_id=OPERATION,
            last_seen_sequence=2,
            last_event_digest=None,
        )

    with pytest.raises(ChatStreamError, match="zero stream cursor"):
        require_resume_cursor(
            operation_id=OPERATION,
            last_seen_sequence=0,
            last_event_digest="a" * 64,
        )


def test_failure_projection_exposes_class_not_internal_payload() -> None:
    snapshot = start_turn(
        operation_id=OPERATION,
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="user-1",
    )
    snapshot = snapshot.apply(
        make_event(
            snapshot,
            TurnState.ADMITTED,
            observed_at=NOW,
        )
    )
    snapshot = snapshot.apply(
        make_event(
            snapshot,
            TurnState.USER_MESSAGE_COMMITTED,
            observed_at=NOW + timedelta(seconds=1),
        )
    )
    failed = make_event(
        snapshot,
        TurnState.FAILED_RETRYABLE,
        observed_at=NOW + timedelta(seconds=2),
        failure_class=FailureClass.RETRYABLE,
        reason_code="provider-timeout",
        payload={"provider_exception": "private stack trace"},
    )
    public = project_turn_event(failed)
    assert public.kind == "turn.failed_retryable"
    assert public.failure_class == "retryable"
    assert public.reason_code == "provider-timeout"
    assert "private stack trace" not in repr(public.as_dict())
