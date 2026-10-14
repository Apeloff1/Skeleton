from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.turn_runtime import (
    BudgetUsage,
    ExecutionBudget,
    RecoveryAction,
    TurnState,
    make_event,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.chat_turn_repository import (
    ChatTurnAuthorizationError,
    ChatTurnBinding,
    ChatTurnConflict,
    ChatTurnCorruption,
    SQLiteChatTurnRepository,
)


NOW = datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)
TENANT = "tenant-a"
OWNER = "owner-a"


def _conversation():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="AI chat",
    )
    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="user-1",
        content="Build more.",
    )
    return thread, user


def _repo(path: Path | str = ":memory:"):
    return SQLiteChatTurnRepository(path)


def _turn(repo: SQLiteChatTurnRepository, *, budget=None):
    thread, user = _conversation()
    binding = ChatTurnBinding.from_conversation(thread, user)
    operation_id = str(uuid4())
    persisted = repo.create_operation(
        operation_id=operation_id,
        request_digest="a" * 64,
        binding=binding,
        budget=budget,
        created_at=NOW,
    )
    return persisted, thread, user


def _advance(repo, turn, state, offset, **kwargs):
    event = make_event(
        turn.snapshot,
        state,
        observed_at=NOW + timedelta(seconds=offset),
        **kwargs,
    )
    return repo.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
    ), event


def test_binding_requires_committed_canonical_user_message() -> None:
    thread, user = _conversation()
    assert ChatTurnBinding.from_conversation(thread, user).thread_id == thread.thread_id

    assistant = replace(
        user,
        message_id=str(uuid4()),
        author_type=ConversationAuthorType.ASSISTANT,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="result",
    )
    with pytest.raises(ChatTurnConflict, match="canonical user"):
        ChatTurnBinding.from_conversation(thread, assistant)

    future = replace(user, message_id=str(uuid4()), sequence=2)
    with pytest.raises(ChatTurnConflict, match="not committed"):
        ChatTurnBinding.from_conversation(thread, future)


def test_operation_creation_is_idempotent_only_for_identical_binding() -> None:
    repo = _repo()
    turn, thread, user = _turn(repo)
    same = repo.create_operation(
        operation_id=turn.snapshot.operation_id,
        request_digest=turn.snapshot.request_digest,
        binding=turn.binding,
        budget=turn.snapshot.budget,
        created_at=NOW + timedelta(seconds=5),
    )
    assert same.snapshot == turn.snapshot
    assert same.created_at == turn.created_at

    different = ChatTurnBinding(
        tenant_id=TENANT,
        owner_id=OWNER,
        thread_id=thread.thread_id,
        causal_user_message_id=user.message_id,
        admitted_thread_version=thread.version + 1,
    )
    with pytest.raises(ChatTurnConflict, match="reused"):
        repo.create_operation(
            operation_id=turn.snapshot.operation_id,
            request_digest=turn.snapshot.request_digest,
            binding=different,
        )


def test_operation_access_is_tenant_owner_bound() -> None:
    repo = _repo()
    turn, _, _ = _turn(repo)
    with pytest.raises(ChatTurnAuthorizationError):
        repo.get_operation(
            turn.snapshot.operation_id,
            tenant_id="tenant-b",
            owner_id=OWNER,
        )


def test_event_append_is_atomic_exact_next_and_idempotent() -> None:
    repo = _repo()
    turn, _, _ = _turn(repo)

    admitted, event = _advance(repo, turn, TurnState.ADMITTED, 1)
    assert admitted.snapshot.state is TurnState.ADMITTED
    assert admitted.snapshot.next_sequence == 2

    duplicate = repo.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert duplicate.snapshot == admitted.snapshot
    assert len(
        repo.list_events(
            turn.snapshot.operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
        )
    ) == 1

    stale = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=2),
        reason_code="different",
    )
    with pytest.raises(ChatTurnConflict, match="reused"):
        repo.append_event(
            stale,
            tenant_id=TENANT,
            owner_id=OWNER,
        )


def test_restart_reconstruction_matches_materialized_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "turns.sqlite3"
    repo = _repo(db)
    turn, _, _ = _turn(repo)
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.VERIFYING,
            TurnState.FINALIZING,
        ),
        start=1,
    ):
        turn, _ = _advance(repo, turn, state, offset)

    operation_id = turn.snapshot.operation_id
    expected = turn.snapshot
    repo.close()

    reopened = _repo(db)
    reconstructed = reopened.reconstruct(
        operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert reconstructed.snapshot == expected
    assert reconstructed.snapshot_digest == turn.snapshot_digest


def test_recovery_decision_is_derived_from_replayed_state(tmp_path: Path) -> None:
    db = tmp_path / "recover.sqlite3"
    repo = _repo(db)
    turn, _, _ = _turn(repo)
    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.TOOL_REQUIRED,
        ),
        start=1,
    ):
        turn, _ = _advance(repo, turn, state, offset)
    turn, _ = _advance(
        repo,
        turn,
        TurnState.TOOL_EXECUTING,
        10,
        tool_call_id="external-1",
        tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
        external_effect_started=True,
    )
    repo.close()

    reopened = _repo(db)
    persisted, decision = reopened.recovery_decision(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert persisted.snapshot.has_ambiguous_external_effect is True
    assert decision.action is RecoveryAction.RECONCILE_TOOL
    assert decision.safe_to_retry is False


def test_budget_usage_is_persisted_and_replayed() -> None:
    budget = ExecutionBudget(
        max_wall_seconds=100,
        max_input_tokens=1000,
        max_output_tokens=500,
        max_model_calls=5,
        max_tool_calls=5,
        max_agent_depth=2,
        max_parallel_workers=2,
        max_retrieval_queries=4,
        max_external_writes=1,
        max_cost_usd=2,
    )
    repo = _repo()
    turn, _, _ = _turn(repo, budget=budget)
    usage = BudgetUsage(
        wall_seconds=1,
        input_tokens=200,
        output_tokens=50,
        model_calls=1,
        cost_usd=0.1,
    )
    event = make_event(
        turn.snapshot,
        TurnState.ADMITTED,
        observed_at=NOW + timedelta(seconds=1),
        usage=usage,
    )
    turn = repo.append_event(
        event,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert turn.snapshot.usage == usage
    assert (
        repo.reconstruct(
            turn.snapshot.operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
        ).snapshot.usage
        == usage
    )


def test_assistant_message_must_match_turn_binding_and_finalization() -> None:
    repo = _repo()
    turn, thread, user = _turn(repo)

    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key="assistant-1",
        content="answer",
        parent_message_id=user.message_id,
        causal_user_message_id=user.message_id,
        operation_id=turn.snapshot.operation_id,
        ai_result_id="result-1",
    )
    with pytest.raises(ChatTurnConflict, match="before finalization"):
        repo.assert_assistant_message_binding(
            assistant,
            tenant_id=TENANT,
            owner_id=OWNER,
        )

    for offset, state in enumerate(
        (
            TurnState.ADMITTED,
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.CONTEXT_COMPILING,
            TurnState.ROUTING,
            TurnState.MODEL_RUNNING,
            TurnState.VERIFYING,
            TurnState.FINALIZING,
        ),
        start=1,
    ):
        turn, _ = _advance(repo, turn, state, offset)

    bound = repo.assert_assistant_message_binding(
        assistant,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert bound.snapshot.state is TurnState.FINALIZING

    wrong_causal = replace(
        assistant,
        message_id=str(uuid4()),
        causal_user_message_id=str(uuid4()),
        parent_message_id=str(uuid4()),
    )
    with pytest.raises(ChatTurnConflict, match="causal user"):
        repo.assert_assistant_message_binding(
            wrong_causal,
            tenant_id=TENANT,
            owner_id=OWNER,
        )


def test_reconstruct_detects_missing_event_row() -> None:
    repo = _repo()
    turn, _, _ = _turn(repo)
    turn, event = _advance(repo, turn, TurnState.ADMITTED, 1)
    repo._connection.execute(
        """
        DELETE FROM ai_chat_turn_event
        WHERE namespace = ? AND operation_id = ? AND sequence = ?
        """,
        (repo.namespace, turn.snapshot.operation_id, event.sequence),
    )
    with pytest.raises(ChatTurnCorruption, match="sequence gap"):
        repo.reconstruct(
            turn.snapshot.operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
        )


def test_reconstruct_detects_materialized_snapshot_tamper() -> None:
    repo = _repo()
    turn, _, _ = _turn(repo)
    turn, _ = _advance(repo, turn, TurnState.ADMITTED, 1)
    repo._connection.execute(
        """
        UPDATE ai_chat_turn_operation
        SET snapshot_digest = ?
        WHERE namespace = ? AND operation_id = ?
        """,
        ("b" * 64, repo.namespace, turn.snapshot.operation_id),
    )
    with pytest.raises(ChatTurnCorruption, match="snapshot digest"):
        repo.get_operation(
            turn.snapshot.operation_id,
            tenant_id=TENANT,
            owner_id=OWNER,
        )
