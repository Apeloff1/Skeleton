from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
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
    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("VS-001 local execution attempted network I/O")
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)

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

@pytest.mark.asyncio
async def test_vs001_rejects_local_model_identity_swap_between_turns(tmp_path) -> None:
    database=tmp_path/"identity-fence.sqlite3"
    repo=SQLiteExecutionRepository(database)
    tools=AsyncToolRuntime()
    original_digest=hashlib.sha256(b"identity-model-v1").hexdigest()
    replacement_digest=hashlib.sha256(b"identity-model-v2").hexdigest()
    holder={}

    def runner(
        request:LocalInferenceRequest,
        cancel:threading.Event,
    )->LocalInferenceResult:
        backend=holder["backend"]
        if request.prompt.startswith("Tool results from the previous provider turn"):
            return LocalInferenceResult(
                text="completed after swap",
                model_id=backend.model_id,
                model_digest=backend.model_digest,
                input_tokens=2,
                output_tokens=3,
                response_id="local:swap-final",
            )
        return LocalInferenceResult(
            text=None,
            model_id=backend.model_id,
            model_digest=backend.model_digest,
            input_tokens=2,
            output_tokens=1,
            finish_reason="tool_calls",
            response_id="local:swap-tool",
            tool_calls=(
                LocalToolCall(
                    call_id="swap-read",
                    tool_id="repo.read",
                    arguments={"path":"README.md"},
                ),
            ),
        )

    backend=CallableLocalModel(
        model_id="identity-model-v1",
        model_digest=original_digest,
        runner=runner,
    )
    holder["backend"]=backend
    adapter=LocalModelAdapter(LocalInferenceEngine(backend))

    async def read_handler(_request):
        backend.model_id="identity-model-v2"
        backend._model_digest=replacement_digest
        return "artifact"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read one path",
            input_schema={
                "type":"object",
                "properties":{"path":{"type":"string"}},
                "required":["path"],
                "additionalProperties":False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
            data_policy="internal:repository",
            network_policy="none",
        ),
        read_handler,
    )

    request=FunctionalAIRequest(
        request_id="vs001-identity-swap",
        objective="Reject model identity changes during execution.",
        prompt="Read README.md.",
        instructions="Stay on one bound local model.",
        context_digest=hashlib.sha256(b"identity-context").hexdigest(),
        allowed_tool_ids=("repo.read",),
        created_at=NOW,
    )
    runtime=FunctionalAIRuntime(
        repo,
        adapter,
        tools,
        verification_hook=lambda *_: ExecutionVerificationDecision(
            passed=True,
            receipt={
                "outcome":"passed",
                "policy_satisfied":True,
                "verifier_id":"identity-test",
                "candidate_digest":hashlib.sha256(b"completed after swap").hexdigest(),
                "context_digest":request.context_digest,
            },
            evidence_refs=("evidence:identity-test",),
        ),
    )

    with pytest.raises(RuntimeError,match="identity changed after binding"):
        await runtime.execute(request)


@pytest.mark.asyncio
async def test_vs001_rejects_identity_drift_before_new_execution(tmp_path) -> None:
    repo=SQLiteExecutionRepository(tmp_path/"pre-run-drift.sqlite3")
    adapter=_local_tool_model()
    runtime=FunctionalAIRuntime(
        repo,
        adapter,
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    adapter.engine.model._model_digest=hashlib.sha256(b"drifted").hexdigest()

    request=FunctionalAIRequest(
        request_id="vs001-pre-run-drift",
        objective="Reject stale runtime identity.",
        prompt="Answer locally.",
        instructions="No identity drift.",
        context_digest=hashlib.sha256(b"pre-run-context").hexdigest(),
        created_at=NOW,
    )
    with pytest.raises(RuntimeError,match="identity changed after binding"):
        await runtime.execute(request)

def _qualification_payload(runtime:FunctionalAIRuntime)->dict[str,object]:
    payload={
        "schema_version":"skeleton.local_model.qualification.v1",
        "status":"qualified",
        "provider":"local",
        "network_required":False,
        "hosted_provider_credentials_required":False,
        "model_id":runtime.local_model.model,
        "model_sha256":runtime.local_model.engine.model.model_digest,
        "executable_sha256":runtime.local_model.runtime_digest,
    }
    encoded=json.dumps(
        payload,
        sort_keys=True,
        separators=(",",":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    payload["receipt_digest"]=hashlib.sha256(encoded).hexdigest()
    return payload


def test_vs001_rejects_mutated_startup_qualification_receipt() -> None:
    runtime=FunctionalAIRuntime(
        SQLiteExecutionRepository(),
        _local_tool_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    receipt=_qualification_payload(runtime)
    runtime._bound_qualification_digest=receipt["receipt_digest"]
    runtime.startup_qualification_receipt=receipt
    receipt["network_required"]=True

    with pytest.raises(RuntimeError,match="receipt was mutated"):
        runtime._assert_startup_qualification_identity()


def test_vs001_rejects_reissued_qualification_receipt_identity() -> None:
    runtime=FunctionalAIRuntime(
        SQLiteExecutionRepository(),
        _local_tool_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    original=_qualification_payload(runtime)
    runtime._bound_qualification_digest=original["receipt_digest"]
    runtime.startup_qualification_receipt=original

    replacement=dict(original)
    replacement["status"]="qualified"
    replacement["probe_nonce"]="different-qualification"
    unsigned=dict(replacement)
    unsigned.pop("receipt_digest",None)
    replacement["receipt_digest"]=hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",",":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    runtime.startup_qualification_receipt=replacement

    with pytest.raises(RuntimeError,match="receipt identity drift"):
        runtime._assert_startup_qualification_identity()


def test_vs001_rejects_startup_qualification_network_or_credentials() -> None:
    runtime=FunctionalAIRuntime(
        SQLiteExecutionRepository(),
        _local_tool_model(),
        AsyncToolRuntime(),
        verification_hook=_verification,
    )
    for field in ("network_required","hosted_provider_credentials_required"):
        receipt=_qualification_payload(runtime)
        receipt[field]=True
        unsigned=dict(receipt)
        unsigned.pop("receipt_digest",None)
        receipt["receipt_digest"]=hashlib.sha256(
            json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",",":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        runtime._bound_qualification_digest=receipt["receipt_digest"]
        runtime.startup_qualification_receipt=receipt
        with pytest.raises(RuntimeError,match="policy drift"):
            runtime._assert_startup_qualification_identity()

