from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import socket
import threading

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRuntime
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_contract import ToolManifest, ToolEffect
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 10, 2, 3, 30, tzinfo=timezone.utc)


def _local_tool_model() -> LocalModelAdapter:
    model_digest = hashlib.sha256(b"vs001-local-model-weights-v1").hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        if request.prompt.startswith("Tool results from the previous provider turn"):
            return LocalInferenceResult(
                text="The local model completed VS-001 from the governed tool receipt.",
                model_id="vs001-local-tool-model",
                model_digest=model_digest,
                input_tokens=len(request.rendered_input.split()),
                output_tokens=11,
                response_id="local:vs001-final",
            )
        assert any(tool.get("tool_id") == "repo.read" for tool in request.tools)
        return LocalInferenceResult(
            text=None,
            model_id="vs001-local-tool-model",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            finish_reason="tool_calls",
            response_id="local:vs001-tool",
            tool_calls=(
                LocalToolCall(
                    call_id="vs001-read-1",
                    tool_id="repo.read",
                    arguments={"path": "README.md"},
                ),
            ),
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="vs001-local-tool-model",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )


def _verification(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    assert candidate.startswith("The local model completed VS-001")
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "vs001:deterministic-independent",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:vs001-governed-tool-receipt",),
    )


@pytest.mark.asyncio
async def test_vs001_local_model_tool_persist_reconnect_end_to_end(
    tmp_path,
    monkeypatch,
) -> None:
    def blocked_socket(*args, **kwargs):
        raise AssertionError("VS-001 local execution attempted network I/O")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    database = tmp_path / "vs001.sqlite3"
    repo = SQLiteExecutionRepository(database)
    tools = AsyncToolRuntime()
    observed = []

    async def read_handler(request):
        observed.append(request)
        return "artifact:readme:vs001"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read one repository path",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
            data_policy="internal:repository",
            network_policy="none",
        ),
        read_handler,
    )

    request = FunctionalAIRequest(
        request_id="vs001-local-e2e",
        objective="Read governed repository context and produce a verified answer.",
        prompt="Read README.md and report completion.",
        instructions="Use only the explicitly provided local tool and local model.",
        context_digest=hashlib.sha256(b"vs001-context").hexdigest(),
        allowed_tool_ids=("repo.read",),
        created_at=NOW,
    )
    runtime = FunctionalAIRuntime(
        repo,
        _local_tool_model(),
        tools,
        verification_hook=_verification,
    )
    run = await runtime.execute(request)

    assert run.execution.completed is True
    assert run.evidence.state == "completed"
    assert run.evidence.status == "completed"
    assert run.evidence.tool_receipt_count == 1
    assert len(run.evidence.provider_receipts) == 2
    assert all(ref.startswith("provider:local:") for ref in run.evidence.provider_receipts)
    assert run.evidence.evidence_refs == ("evidence:vs001-governed-tool-receipt",)
    assert len(observed) == 1
    assert observed[0].tool_id == "repo.read"
    assert dict(observed[0].arguments) == {"path": "README.md"}

    # Re-open the durable database as a distinct runtime process would.
    recovered = SQLiteExecutionRepository(database)
    stored = recovered.result(request.execution_id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.final_output == run.execution.result.final_output
    assert stored.stream_terminal_event == run.evidence.stream_terminal_event
    assert len(recovered.turns(request.execution_id)) == 3


def test_vs001_rejects_non_local_model_adapter() -> None:
    class NotLocal:
        provider_id = "hosted"

    with pytest.raises(TypeError, match="LocalModelAdapter"):
        FunctionalAIRuntime(
            SQLiteExecutionRepository(),
            NotLocal(),  # type: ignore[arg-type]
            AsyncToolRuntime(),
            verification_hook=_verification,
        )
