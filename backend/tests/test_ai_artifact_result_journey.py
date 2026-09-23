from __future__ import annotations

from datetime import datetime, timezone

from core.gameforge_artifact_builder import build_source_artifact
from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    AIExecutionResult,
    ExecutionState,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _now() -> datetime:
    return datetime(2026, 9, 23, 22, 0, tzinfo=timezone.utc)


def _request() -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="artifact-op-1",
        execution_id="artifact-exec-1",
        objective="Build and persist an artifact result.",
        context_policy={"tenant_id": "tenant-a"},
        tool_policy={"allowed_tool_ids": []},
        resource_budget={
            "max_model_turns": 1,
            "max_tool_calls": 1,
        },
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=_now(),
    )


def _advance_to_verifying(repo: SQLiteExecutionRepository):
    current = repo.create(_request(), now=_now())
    for state in (
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
        ExecutionState.VERIFYING,
    ):
        current = repo.transition(
            current.execution_id,
            state,
            expected_version=current.version,
            now=_now(),
        )
    return current


def test_deterministic_artifact_is_bound_to_durable_execution_result(
    tmp_path,
) -> None:
    artifact = build_source_artifact(
        "golden-artifact",
        files=[
            {
                "filename": "main.py",
                "content": "print('artifact')\n",
            }
        ],
        artifacts_root=tmp_path / "artifacts",
        build_token="artifact-op-1",
        built_at=1_700_000_000,
    )
    artifact_ref = (
        "artifact:sha256:"
        + artifact["sha256"]
        + ":"
        + artifact["filename"]
    )

    db_path = tmp_path / "execution.sqlite3"
    repo = SQLiteExecutionRepository(db_path)
    current = _advance_to_verifying(repo)
    result = AIExecutionResult(
        operation_id=current.operation_id,
        execution_id=current.execution_id,
        status="completed",
        final_output="artifact ready",
        verification="verification:artifact-golden",
        artifact_refs=(artifact_ref,),
        usage={"artifact_count": 1},
        completed_at=_now(),
    )

    terminal = repo.finalize(
        result,
        expected_execution_version=current.version,
        now=_now(),
    )

    assert terminal.state is ExecutionState.COMPLETED
    persisted = repo.result(current.execution_id)
    assert persisted is not None
    assert persisted.artifact_refs == (artifact_ref,)
    assert artifact["sha256"] in persisted.artifact_refs[0]
    assert artifact["filename"] in persisted.artifact_refs[0]
    assert (tmp_path / "artifacts" / artifact["filename"]).is_file()
    repo.close()

    restarted = SQLiteExecutionRepository(db_path)
    recovered = restarted.result("artifact-exec-1")
    assert recovered is not None
    assert recovered.artifact_refs == (artifact_ref,)
    assert recovered.final_output == "artifact ready"
    assert len(restarted.pending_outbox(execution_id="artifact-exec-1")) == 1
    restarted.close()
