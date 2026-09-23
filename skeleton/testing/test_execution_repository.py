from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    AIExecutionResult,
    AgentTurn,
    ExecutionState,
)
from skeleton.persistence.execution_repository import (
    ExecutionRepositoryConflict,
    SQLiteExecutionRepository,
)


def _now() -> datetime:
    return datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)


def _request() -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="op-1",
        execution_id="exec-1",
        objective="Answer the user request.",
        context_policy={"policy": "default"},
        tool_policy={"mode": "scoped"},
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 8,
            "max_repairs": 1,
        },
        stop_policy={"max_turns": 4},
        created_at=_now(),
    )


def _advance_to_provider_completed(
    repo: SQLiteExecutionRepository,
    execution_id: str,
):
    current = repo.get(execution_id)
    for state in (
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
    ):
        current = repo.transition(
            execution_id,
            state,
            expected_version=current.version,
            now=_now(),
        )
    return current


def test_execution_request_serialization_is_stable() -> None:
    request = _request()

    payload = request.as_dict()

    assert payload["operation_id"] == "op-1"
    assert payload["execution_id"] == "exec-1"
    assert payload["identity_digest"] == request.identity_digest
    assert payload["resource_budget"]["max_model_turns"] == 4


def test_repository_survives_restart_and_preserves_execution_version(tmp_path) -> None:
    path = tmp_path / "execution.sqlite3"
    first = SQLiteExecutionRepository(path)
    created = first.create(_request(), now=_now())
    loading = first.transition(
        created.execution_id,
        ExecutionState.LOADING,
        expected_version=created.version,
        now=_now() + timedelta(seconds=1),
    )
    first.close()

    reopened = SQLiteExecutionRepository(path)
    restored = reopened.get("exec-1")

    assert restored.state is ExecutionState.LOADING
    assert restored.version == loading.version
    assert restored.request.identity_digest == _request().identity_digest


def test_checkpoint_compare_and_set_rejects_stale_writer() -> None:
    repo = SQLiteExecutionRepository()
    created = repo.create(_request(), now=_now())

    checkpoint = repo.checkpoint(
        created.execution_id,
        {"phase": "created", "provider_receipts": []},
        expected_execution_version=created.version,
        expected_checkpoint_version=0,
        now=_now(),
    )

    assert checkpoint.checkpoint_version == 1
    assert checkpoint.payload["phase"] == "created"
    current = repo.get(created.execution_id)
    assert current.checkpoint_version == 1

    with pytest.raises(
        ExecutionRepositoryConflict,
        match="checkpoint version changed",
    ):
        repo.checkpoint(
            created.execution_id,
            {"phase": "stale"},
            expected_execution_version=current.version,
            expected_checkpoint_version=0,
            now=_now(),
        )


def test_turn_lineage_is_strictly_monotonic_and_immutable() -> None:
    repo = SQLiteExecutionRepository()
    current = repo.create(_request(), now=_now())
    root = AgentTurn(
        operation_id="op-1",
        execution_id="exec-1",
        turn_id="turn-0",
        parent_turn_id=None,
        turn_index=0,
        phase=ExecutionState.PROVIDER_COMPLETED,
        context_digest="a" * 64,
        checkpoint_ref="execution-checkpoint:exec-1:0",
        status="provider_completed",
    )
    current = repo.append_turn(
        root,
        expected_execution_version=current.version,
        now=_now(),
    )
    child = AgentTurn(
        operation_id="op-1",
        execution_id="exec-1",
        turn_id="turn-1",
        parent_turn_id="turn-0",
        turn_index=1,
        phase=ExecutionState.TOOL_COMPLETED,
        context_digest="b" * 64,
        checkpoint_ref="execution-checkpoint:exec-1:1",
        status="tool_completed",
    )
    current = repo.append_turn(
        child,
        expected_execution_version=current.version,
        now=_now(),
    )

    assert [turn.turn_id for turn in repo.turns("exec-1")] == [
        "turn-0",
        "turn-1",
    ]

    wrong_parent = AgentTurn(
        operation_id="op-1",
        execution_id="exec-1",
        turn_id="turn-2",
        parent_turn_id="turn-does-not-exist",
        turn_index=2,
        phase=ExecutionState.PROVIDER_COMPLETED,
        context_digest="c" * 64,
        checkpoint_ref="execution-checkpoint:exec-1:2",
        status="provider_completed",
    )
    with pytest.raises(
        ExecutionRepositoryConflict,
        match="parent",
    ):
        repo.append_turn(
            wrong_parent,
            expected_execution_version=current.version,
            now=_now(),
        )


def test_atomic_finalization_commits_result_before_terminal_outbox() -> None:
    repo = SQLiteExecutionRepository()
    repo.create(_request(), now=_now())
    current = _advance_to_provider_completed(repo, "exec-1")
    current = repo.transition(
        "exec-1",
        ExecutionState.VERIFYING,
        expected_version=current.version,
        now=_now(),
    )
    result = AIExecutionResult(
        operation_id="op-1",
        execution_id="exec-1",
        status="completed",
        final_output="artifact:final-answer",
        verification="verification:ver-1",
        route_receipts=("route:r1",),
        provider_receipts=("provider:resp-1",),
        tool_receipts=("tool:receipt-1",),
        memory_refs=("memory:m1",),
        artifact_refs=("artifact:final-answer",),
        usage={"input_tokens": 20, "output_tokens": 10},
        stream_terminal_event="stream:event-terminal",
        completed_at=_now(),
    )

    terminal = repo.finalize(
        result,
        expected_execution_version=current.version,
        now=_now(),
    )

    assert terminal.state is ExecutionState.COMPLETED
    assert repo.result("exec-1") == result
    pending = repo.pending_outbox(execution_id="exec-1")
    assert len(pending) == 1
    assert pending[0].event_type == "execution.completed"
    assert pending[0].payload["result_ref"] == "execution-result:exec-1"
    assert pending[0].payload["verification"] == "verification:ver-1"


def test_finalization_replay_does_not_duplicate_terminal_event() -> None:
    repo = SQLiteExecutionRepository()
    repo.create(_request(), now=_now())
    current = _advance_to_provider_completed(repo, "exec-1")
    current = repo.transition(
        "exec-1",
        ExecutionState.VERIFYING,
        expected_version=current.version,
        now=_now(),
    )
    result = AIExecutionResult(
        operation_id="op-1",
        execution_id="exec-1",
        status="completed",
        final_output="artifact:final",
        verification="verification:ver-1",
        usage={},
        completed_at=_now(),
    )

    terminal = repo.finalize(
        result,
        expected_execution_version=current.version,
        now=_now(),
    )
    replay = repo.finalize(
        result,
        expected_execution_version=current.version,
        now=_now(),
    )

    assert replay.state is ExecutionState.COMPLETED
    assert replay.version == terminal.version
    assert len(repo.pending_outbox(execution_id="exec-1")) == 1


def test_recoverable_returns_nonterminal_execution_after_restart(tmp_path) -> None:
    path = tmp_path / "execution.sqlite3"
    repo = SQLiteExecutionRepository(path)
    created = repo.create(_request(), now=_now())
    repo.transition(
        created.execution_id,
        ExecutionState.LOADING,
        expected_version=created.version,
        now=_now(),
    )
    repo.close()

    reopened = SQLiteExecutionRepository(path)
    recovered = reopened.recoverable()

    assert len(recovered) == 1
    assert recovered[0].execution_id == "exec-1"
    assert recovered[0].state is ExecutionState.LOADING


def test_stale_transition_is_rejected() -> None:
    repo = SQLiteExecutionRepository()
    created = repo.create(_request(), now=_now())
    repo.transition(
        "exec-1",
        ExecutionState.LOADING,
        expected_version=created.version,
        now=_now(),
    )

    with pytest.raises(
        ExecutionRepositoryConflict,
        match="version changed",
    ):
        repo.transition(
            "exec-1",
            ExecutionState.LOADING,
            expected_version=created.version,
            now=_now(),
        )
