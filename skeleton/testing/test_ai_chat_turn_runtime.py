from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.turn_runtime import (
    BudgetGovernor,
    BudgetUsage,
    ExecutionBudget,
    FailureClass,
    RecoveryAction,
    RecoveryPlanner,
    TurnEvent,
    TurnJournal,
    TurnRuntimeError,
    TurnState,
    make_event,
    operation_digest,
    start_turn,
)


NOW = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
REQUEST_DIGEST = "a" * 64


def _initial(*, budget: ExecutionBudget | None = None):
    return start_turn(
        operation_id="op-1",
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="user-message-1",
        budget=budget,
    )


def _advance(snapshot, state: TurnState, offset: int, **kwargs):
    event = make_event(
        snapshot,
        state,
        observed_at=NOW + timedelta(seconds=offset),
        **kwargs,
    )
    return snapshot.apply(event), event


def _to_model():
    snapshot = _initial()
    events = []
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
        ),
        start=1,
    ):
        snapshot, event = _advance(snapshot, state, offset)
        events.append(event)
    return snapshot, events


def test_happy_path_is_digest_chained_and_replayable() -> None:
    snapshot, events = _to_model()
    for offset, state in enumerate(
        (
            TurnState.VERIFYING,
            TurnState.FINALIZING,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            TurnState.MEMORY_PROPOSAL,
            TurnState.COMPLETE,
        ),
        start=10,
    ):
        snapshot, event = _advance(snapshot, state, offset)
        events.append(event)

    assert snapshot.state is TurnState.COMPLETE
    assert snapshot.terminal is True
    assert snapshot.next_sequence == len(events) + 1
    assert all(len(event.digest) == 64 for event in events)
    assert events[0].previous_event_digest is None
    for previous, current in zip(events, events[1:]):
        assert current.previous_event_digest == previous.digest

    replayed = TurnJournal.replay(_initial(), events)
    assert replayed == snapshot
    assert operation_digest(replayed) == operation_digest(snapshot)


def test_illegal_transition_fails_closed() -> None:
    snapshot = _initial()
    with pytest.raises(TurnRuntimeError, match="illegal turn transition"):
        make_event(
            snapshot,
            TurnState.MODEL_RUNNING,
            observed_at=NOW,
        )


def test_event_cannot_be_applied_to_wrong_operation_or_sequence() -> None:
    snapshot = _initial()
    admitted = make_event(snapshot, TurnState.ADMITTED, observed_at=NOW)

    other = start_turn(
        operation_id="op-2",
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="user-message-1",
    )
    with pytest.raises(TurnRuntimeError, match="different operation"):
        other.apply(admitted)

    snapshot = snapshot.apply(admitted)
    stale = TurnEvent(
        operation_id=snapshot.operation_id,
        request_digest=snapshot.request_digest,
        sequence=1,
        from_state=snapshot.state,
        to_state=TurnState.USER_MESSAGE_COMMITTED,
        observed_at=NOW + timedelta(seconds=1),
        previous_event_digest=snapshot.last_event_digest,
    )
    with pytest.raises(TurnRuntimeError, match="next durable sequence"):
        snapshot.apply(stale)


def test_digest_chain_tamper_is_rejected() -> None:
    snapshot = _initial()
    snapshot, first = _advance(snapshot, TurnState.ADMITTED, 1)
    event = TurnEvent(
        operation_id=snapshot.operation_id,
        request_digest=snapshot.request_digest,
        sequence=snapshot.next_sequence,
        from_state=snapshot.state,
        to_state=TurnState.USER_MESSAGE_COMMITTED,
        observed_at=NOW + timedelta(seconds=2),
        previous_event_digest="b" * 64,
    )
    with pytest.raises(TurnRuntimeError, match="digest chain is broken"):
        snapshot.apply(event)

    verified, errors = TurnJournal.verify(_initial(), (first, event))
    assert verified.state is TurnState.ADMITTED
    assert len(errors) == 1
    assert "digest chain is broken" in errors[0]


def test_consequential_tool_ambiguity_requires_reconciliation() -> None:
    snapshot, _ = _to_model()
    snapshot, _ = _advance(snapshot, TurnState.TOOL_REQUIRED, 10)
    snapshot, _ = _advance(
        snapshot,
        TurnState.TOOL_EXECUTING,
        11,
        tool_call_id="tool-1",
        tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
        external_effect_started=True,
    )

    assert snapshot.has_ambiguous_external_effect is True
    decision = RecoveryPlanner.plan(snapshot)
    assert decision.action is RecoveryAction.RECONCILE_TOOL
    assert decision.safe_to_retry is False
    assert decision.requires_receipt_reconciliation is True

    retry = make_event(
        snapshot,
        TurnState.FAILED_RETRYABLE,
        observed_at=NOW + timedelta(seconds=12),
        failure_class=FailureClass.RETRYABLE,
    )
    with pytest.raises(TurnRuntimeError, match="must be reconciled"):
        snapshot.apply(retry)

    continuation = make_event(
        snapshot,
        TurnState.MODEL_RUNNING,
        observed_at=NOW + timedelta(seconds=13),
    )
    with pytest.raises(TurnRuntimeError, match="must be reconciled"):
        snapshot.apply(continuation)


def test_read_only_tool_can_be_retried_after_restart() -> None:
    snapshot, _ = _to_model()
    snapshot, _ = _advance(snapshot, TurnState.TOOL_REQUIRED, 10)
    snapshot, _ = _advance(
        snapshot,
        TurnState.TOOL_EXECUTING,
        11,
        tool_call_id="tool-read",
        tool_side_effect=SideEffectClass.READ_ONLY,
    )
    decision = RecoveryPlanner.plan(snapshot)
    assert decision.action is RecoveryAction.RETRY_TOOL
    assert decision.safe_to_retry is True
    assert decision.requires_receipt_reconciliation is False


def test_durable_tool_receipt_allows_model_continuation() -> None:
    snapshot, _ = _to_model()
    snapshot, _ = _advance(snapshot, TurnState.TOOL_REQUIRED, 10)
    snapshot, _ = _advance(
        snapshot,
        TurnState.TOOL_EXECUTING,
        11,
        tool_call_id="tool-write",
        tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
        external_effect_started=True,
    )
    snapshot, event = _advance(
        snapshot,
        TurnState.MODEL_RUNNING,
        12,
        tool_receipt_ref="tool-receipt://tool-write/1",
    )
    assert event.tool_receipt_ref == "tool-receipt://tool-write/1"
    assert snapshot.state is TurnState.MODEL_RUNNING
    assert snapshot.pending_tool_call_id is None
    assert snapshot.pending_tool_receipt_ref is None
    assert snapshot.external_effect_started is False


def test_tool_receipt_present_during_execution_resumes_verification() -> None:
    snapshot, _ = _to_model()
    snapshot, _ = _advance(snapshot, TurnState.TOOL_REQUIRED, 10)
    snapshot, _ = _advance(
        snapshot,
        TurnState.TOOL_EXECUTING,
        11,
        tool_call_id="tool-write",
        tool_side_effect=SideEffectClass.REVERSIBLE_WRITE,
        external_effect_started=True,
        tool_receipt_ref="tool-receipt://tool-write/1",
    )
    decision = RecoveryPlanner.plan(snapshot)
    assert decision.action is RecoveryAction.RESUME_VERIFICATION
    assert decision.safe_to_retry is False


def test_budget_is_hard_and_event_usage_cannot_exceed_it() -> None:
    budget = ExecutionBudget(
        max_wall_seconds=20,
        max_input_tokens=100,
        max_output_tokens=50,
        max_model_calls=2,
        max_tool_calls=2,
        max_agent_depth=1,
        max_parallel_workers=1,
        max_retrieval_queries=2,
        max_external_writes=1,
        max_cost_usd=0.50,
    )
    snapshot = _initial(budget=budget)
    usage = BudgetUsage(
        wall_seconds=1,
        input_tokens=101,
    )
    event = make_event(
        snapshot,
        TurnState.ADMITTED,
        observed_at=NOW,
        usage=usage,
    )
    with pytest.raises(TurnRuntimeError, match="turn budget exceeded: input_tokens"):
        snapshot.apply(event)


def test_budget_usage_increment_rejects_unknown_or_negative_dimensions() -> None:
    usage = BudgetUsage()
    assert usage.add(model_calls=1, input_tokens=20).model_calls == 1

    with pytest.raises(TurnRuntimeError, match="unknown usage dimensions"):
        usage.add(unknown_counter=1)

    with pytest.raises(TurnRuntimeError, match="cannot be negative"):
        usage.add(model_calls=-1)


def test_child_budget_cannot_amplify_remaining_parent_authority() -> None:
    parent = ExecutionBudget(
        max_wall_seconds=100,
        max_input_tokens=1000,
        max_output_tokens=500,
        max_model_calls=5,
        max_tool_calls=10,
        max_agent_depth=4,
        max_parallel_workers=8,
        max_retrieval_queries=10,
        max_external_writes=2,
        max_cost_usd=5,
    )
    used = BudgetUsage(
        wall_seconds=10,
        input_tokens=400,
        model_calls=2,
        external_writes=1,
        cost_usd=1.5,
    )
    child = ExecutionBudget(
        max_wall_seconds=50,
        max_input_tokens=500,
        max_output_tokens=200,
        max_model_calls=2,
        max_tool_calls=4,
        max_agent_depth=2,
        max_parallel_workers=2,
        max_retrieval_queries=3,
        max_external_writes=1,
        max_cost_usd=2,
    )
    assert BudgetGovernor.child_budget(parent, used, child) is child

    amplified = ExecutionBudget(
        max_wall_seconds=50,
        max_input_tokens=700,
        max_output_tokens=200,
        max_model_calls=2,
        max_tool_calls=4,
        max_agent_depth=2,
        max_parallel_workers=2,
        max_retrieval_queries=3,
        max_external_writes=1,
        max_cost_usd=2,
    )
    with pytest.raises(TurnRuntimeError, match="amplifies remaining authority"):
        BudgetGovernor.child_budget(parent, used, amplified)


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (TurnState.RECEIVED, RecoveryAction.RESUME_ADMISSION),
        (TurnState.ADMITTED, RecoveryAction.RESUME_MESSAGE_COMMIT),
        (TurnState.USER_MESSAGE_COMMITTED, RecoveryAction.RESUME_CONTEXT),
        (TurnState.CONTEXT_COMPILING, RecoveryAction.RESUME_CONTEXT),
        (TurnState.ROUTING, RecoveryAction.RESUME_ROUTING),
        (TurnState.MODEL_RUNNING, RecoveryAction.RETRY_MODEL),
        (TurnState.TOOL_REQUIRED, RecoveryAction.RESUME_TOOL_ADMISSION),
        (TurnState.AWAITING_USER, RecoveryAction.WAIT_FOR_USER),
        (TurnState.VERIFYING, RecoveryAction.RESUME_VERIFICATION),
        (TurnState.FINALIZING, RecoveryAction.RESUME_FINALIZATION),
        (
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            RecoveryAction.RESUME_MEMORY,
        ),
        (TurnState.MEMORY_PROPOSAL, RecoveryAction.FINALIZE_COMPLETE),
    ),
)
def test_recovery_map_is_explicit(state: TurnState, expected: RecoveryAction) -> None:
    snapshot, _ = _to_model()
    if state in {
        TurnState.RECEIVED,
        TurnState.ADMITTED,
        TurnState.USER_MESSAGE_COMMITTED,
        TurnState.CONTEXT_COMPILING,
        TurnState.ROUTING,
        TurnState.MODEL_RUNNING,
    }:
        snapshot = _initial()
        path = [
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
        ]
        if state is not TurnState.RECEIVED:
            for offset, target in enumerate(path, start=1):
                snapshot, _ = _advance(snapshot, target, offset)
                if target is state:
                    break
    elif state is TurnState.TOOL_REQUIRED:
        snapshot, _ = _advance(snapshot, TurnState.TOOL_REQUIRED, 10)
    elif state is TurnState.AWAITING_USER:
        snapshot, _ = _advance(snapshot, TurnState.AWAITING_USER, 10)
    elif state is TurnState.VERIFYING:
        snapshot, _ = _advance(snapshot, TurnState.VERIFYING, 10)
    elif state is TurnState.FINALIZING:
        snapshot, _ = _advance(snapshot, TurnState.VERIFYING, 10)
        snapshot, _ = _advance(snapshot, TurnState.FINALIZING, 11)
    elif state is TurnState.ASSISTANT_MESSAGE_COMMITTED:
        snapshot, _ = _advance(snapshot, TurnState.VERIFYING, 10)
        snapshot, _ = _advance(snapshot, TurnState.FINALIZING, 11)
        snapshot, _ = _advance(
            snapshot,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            12,
        )
    elif state is TurnState.MEMORY_PROPOSAL:
        snapshot, _ = _advance(snapshot, TurnState.VERIFYING, 10)
        snapshot, _ = _advance(snapshot, TurnState.FINALIZING, 11)
        snapshot, _ = _advance(
            snapshot,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            12,
        )
        snapshot, _ = _advance(snapshot, TurnState.MEMORY_PROPOSAL, 13)

    decision = RecoveryPlanner.plan(snapshot)
    assert decision.action is expected


@pytest.mark.parametrize(
    "terminal",
    (
        TurnState.COMPLETE,
        TurnState.DEGRADED,
        TurnState.FAILED_RETRYABLE,
        TurnState.FAILED_TERMINAL,
        TurnState.CANCELLED,
        TurnState.QUARANTINED,
    ),
)
def test_terminal_snapshots_do_not_restart_work(terminal: TurnState) -> None:
    snapshot, _ = _to_model()
    if terminal is TurnState.COMPLETE:
        snapshot, _ = _advance(snapshot, TurnState.VERIFYING, 10)
        snapshot, _ = _advance(snapshot, TurnState.FINALIZING, 11)
        snapshot, _ = _advance(
            snapshot,
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            12,
        )
        snapshot, _ = _advance(snapshot, TurnState.COMPLETE, 13)
    elif terminal is TurnState.DEGRADED:
        snapshot, _ = _advance(snapshot, TurnState.DEGRADED, 10)
    elif terminal is TurnState.FAILED_RETRYABLE:
        snapshot, _ = _advance(
            snapshot,
            TurnState.FAILED_RETRYABLE,
            10,
            failure_class=FailureClass.RETRYABLE,
        )
    elif terminal is TurnState.FAILED_TERMINAL:
        snapshot, _ = _advance(
            snapshot,
            TurnState.FAILED_TERMINAL,
            10,
            failure_class=FailureClass.TERMINAL,
        )
    elif terminal is TurnState.CANCELLED:
        snapshot, _ = _advance(
            snapshot,
            TurnState.CANCELLED,
            10,
            failure_class=FailureClass.CANCELLED,
        )
    else:
        snapshot, _ = _advance(
            snapshot,
            TurnState.QUARANTINED,
            10,
            failure_class=FailureClass.QUARANTINE,
        )

    decision = RecoveryPlanner.plan(snapshot)
    assert decision.action is RecoveryAction.NOOP_TERMINAL
    assert decision.safe_to_retry is False


def test_quarantine_requires_explicit_failure_class() -> None:
    snapshot, _ = _to_model()
    with pytest.raises(TurnRuntimeError, match="quarantine transition requires"):
        make_event(
            snapshot,
            TurnState.QUARANTINED,
            observed_at=NOW,
        )

    event = make_event(
        snapshot,
        TurnState.QUARANTINED,
        observed_at=NOW,
        failure_class=FailureClass.POLICY,
    )
    assert snapshot.apply(event).state is TurnState.QUARANTINED


def test_operation_digest_changes_when_durable_state_changes() -> None:
    snapshot = _initial()
    initial_digest = operation_digest(snapshot)
    snapshot, _ = _advance(snapshot, TurnState.ADMITTED, 1)
    assert operation_digest(snapshot) != initial_digest
    assert len(operation_digest(snapshot)) == 64
