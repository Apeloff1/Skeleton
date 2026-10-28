from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import socket
import threading
from uuid import uuid4

import pytest

from skeleton.ai.model_runtime import NativeLLMRuntime, RuntimeContractError
from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalModelAdapter,
    LocalModelArtifactError,
    NativeRuntimeBackendError,
    NativeRuntimeLocalModel,
    load_local_model_artifact,
    write_local_model_artifact,
)
from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.cortex.transformer import TinyTransformer
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRegistry, ProviderRequest, ProviderResponse
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _native_backend() -> NativeRuntimeLocalModel:
    model = TinyTransformer(
        vocab=(
            "system:",
            "user:",
            "assistant:",
            "alpha",
            "beta",
            "gamma",
            "delta",
            "answer",
        ),
        dim=8,
        ctx=32,
        seed=41,
        n_heads=2,
        n_layers=2,
        d_ff=16,
    )
    return NativeRuntimeLocalModel(NativeLLMRuntime(model))


def _write_native(tmp_path):
    backend = _native_backend()
    path = tmp_path / "native-runtime.json"
    receipt = write_local_model_artifact(backend, path)
    return path, backend, receipt


def _local_env(monkeypatch, path) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "8")
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "19")
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def _block_internet(monkeypatch) -> None:
    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("native local model attempted Internet socket I/O")
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)


def test_native_runtime_checkpoint_round_trips_as_local_artifact(tmp_path) -> None:
    path, expected, receipt = _write_native(tmp_path)

    loaded = load_local_model_artifact(path)

    assert isinstance(loaded.model, NativeRuntimeLocalModel)
    assert loaded.model.model_id == expected.model_id
    assert loaded.model.model_digest == expected.model_digest
    assert loaded.model.runtime_digest == expected.runtime_digest
    assert loaded.model.tokenizer_digest == expected.tokenizer_digest
    assert loaded.receipt.schema == "skeleton.ai.native-llm-runtime.v2"
    assert loaded.receipt.model_digest == expected.model_digest
    assert loaded.receipt.artifact_sha256 == receipt.artifact_sha256
    assert json.loads(path.read_text(encoding="utf-8"))["digest"]


@pytest.mark.asyncio
async def test_native_runtime_executes_through_local_inference_engine(tmp_path) -> None:
    path, expected, _receipt = _write_native(tmp_path)
    loaded = load_local_model_artifact(path)
    engine = LocalInferenceEngine(loaded.model, cache_size=4)
    request = LocalInferenceRequest(
        prompt="alpha beta",
        instructions="answer",
        max_output_tokens=4,
        seed=7,
    )

    first = await engine.generate(request)
    second = await engine.generate(request)

    assert first.model_id == expected.model_id
    assert first.model_digest == expected.model_digest
    assert first.input_tokens > 0
    assert 0 < first.output_tokens <= 4
    assert first.text
    assert first.cached is False
    assert second.cached is True
    assert second.text == first.text
    assert second.model_digest == first.model_digest
    assert len(first.execution_receipt_digest) == 64
    assert second.execution_receipt_digest == first.execution_receipt_digest


@pytest.mark.asyncio
async def test_provider_registry_activates_native_runtime_artifact_offline(
    tmp_path,
    monkeypatch,
) -> None:
    path, expected, _receipt = _write_native(tmp_path)
    _local_env(monkeypatch, path)
    _block_internet(monkeypatch)

    registry = ProviderRegistry.from_env()
    adapter = registry.require_active()
    status = registry.statuses()

    assert isinstance(adapter, LocalModelAdapter)
    assert adapter.provider_id == "local"
    assert adapter.model == expected.model_id
    assert adapter.runtime_digest == expected.runtime_digest
    assert status[0]["network_policy"] == "none"
    assert status[0]["artifact"]["schema"] == "skeleton.ai.native-llm-runtime.v2"
    assert status[0]["artifact"]["model_digest"] == expected.model_digest

    response = await adapter.generate(
        ProviderRequest(
            instructions="answer",
            prompt="alpha beta",
            max_output_tokens=3,
            operation_id="op-native-provider",
            execution_id="exec-native-provider",
            turn_id="turn-native-provider",
        )
    )
    assert response.provider == "local"
    assert response.model == expected.model_id
    assert response.text
    assert response.usage.input_tokens > 0
    assert 0 < response.usage.output_tokens <= 3
    assert response.usage.billed_cost == "0"
    assert response.usage.usage_source == "local_model"
    assert isinstance(response.execution_receipt_digest, str)
    assert len(response.execution_receipt_digest) == 64


def test_native_runtime_execution_receipts_bind_exact_context_identity() -> None:
    backend = _native_backend()
    first_request = LocalInferenceRequest(
        prompt="alpha beta", max_output_tokens=2, seed=17, context_digest="a" * 64,
    )
    second_request = LocalInferenceRequest(
        prompt="alpha beta", max_output_tokens=2, seed=17, context_digest="b" * 64,
    )
    first = backend.infer(first_request, threading.Event())
    second = backend.infer(second_request, threading.Event())
    assert first.text == second.text
    assert first.execution_receipt_digest != second.execution_receipt_digest
    assert len(first.execution_receipt_digest) == 64
    with pytest.raises(ValueError, match="execution_receipt_digest"):
        replace(first, execution_receipt_digest="not-a-digest")
    with pytest.raises(ValueError, match="execution_receipt_digest"):
        ProviderResponse(
            text="alpha", provider="local", model="test",
            execution_receipt_digest="malformed",
        )


def test_native_runtime_backend_honors_precancel() -> None:
    backend = _native_backend()
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(LocalInferenceCancelled):
        backend.infer(
            LocalInferenceRequest(prompt="alpha", max_output_tokens=2),
            cancel,
        )


def test_native_runtime_structured_output_protocol_validates_schema() -> None:
    backend = _native_backend()
    request = LocalInferenceRequest(
        prompt="alpha",
        max_output_tokens=2,
        structured_output_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
            "additionalProperties": False,
        },
    )
    text, calls, structured, finish = backend._parse_output(
        '{"answer":"beta"}',
        request,
    )
    assert text is None
    assert calls == ()
    assert structured == {"answer": "beta"}
    assert finish == "completed"

    with pytest.raises(
        NativeRuntimeBackendError,
        match="structured output validation failed",
    ):
        backend._parse_output('{"answer":7}', request)

    non_object = LocalInferenceRequest(
        prompt="alpha",
        structured_output_schema={
            "type": "array",
            "items": {"type": "string"},
        },
    )
    with pytest.raises(
        NativeRuntimeBackendError,
        match="must describe an object",
    ):
        backend._render_prompt(non_object)


def test_native_runtime_tool_protocol_enforces_declared_ids() -> None:
    backend = _native_backend()
    request = LocalInferenceRequest(
        prompt="alpha",
        max_output_tokens=2,
        tools=(
            {
                "tool_id": "repo.read",
                "description": "read",
                "input_schema": {"type": "object"},
            },
        ),
    )
    raw = (
        '{"skeleton_local_response":1,"tool_calls":['
        '{"call_id":"call-1","tool_id":"repo.read","arguments":{}}]}'
    )
    text, calls, structured, finish = backend._parse_output(raw, request)
    assert text is None
    assert structured is None
    assert finish == "tool_calls"
    assert calls[0].tool_id == "repo.read"

    with pytest.raises(NativeRuntimeBackendError, match="undeclared tool_id"):
        backend._parse_output(raw.replace("repo.read", "repo.write"), request)

    with pytest.raises(
        NativeRuntimeBackendError,
        match="unsupported native local response protocol version",
    ):
        backend._parse_output(
            raw.replace(
                '"skeleton_local_response":1',
                '"skeleton_local_response":true',
            ),
            request,
        )

    with pytest.raises(NativeRuntimeBackendError, match="duplicate JSON key"):
        backend._parse_output(
            '{"skeleton_local_response":1,'
            '"skeleton_local_response":1,"text":"alpha"}',
            request,
        )


def test_native_runtime_artifact_tamper_fails_closed(tmp_path) -> None:
    path, _backend, _receipt = _write_native(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["model"]["bout"][0] += 0.25
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(
        LocalModelArtifactError,
        match="native runtime artifact failed identity validation",
    ):
        load_local_model_artifact(path)


def test_native_runtime_backend_identity_detects_weight_drift() -> None:
    backend = _native_backend()
    backend.runtime.model.bout[0] += 0.5

    with pytest.raises(RuntimeContractError):
        backend.infer(
            LocalInferenceRequest(prompt="alpha", max_output_tokens=1),
            threading.Event(),
        )


def _engine_command():
    now = datetime.now(timezone.utc)
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-native",
        actor_id="operator-native",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=2),
        idempotency_key="native-runtime-local-provider",
        trace_id="trace-native-runtime-local-provider",
    )
    execution_id = str(uuid4())
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=str(uuid4()),
        tenant_id=operation.tenant_id,
        context_id=str(uuid4()),
        context_digest="a" * 64,
        compiler_version="native-runtime-local-provider-test",
        source_snapshot=((str(uuid4()), "b" * 64),),
        data_class="internal",
        instructions="answer",
        prompt="alpha beta",
        purpose="model-inference",
        history=(),
    )
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="Execute the canonical native runtime through the local provider.",
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "source_snapshot": [list(item) for item in handoff.source_snapshot],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "data_class": "internal",
            "purpose": "tool-execution",
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 2,
            "max_tool_calls": 1,
            "max_output_tokens": 4,
        },
        stop_policy={
            "deadline": operation.deadline.isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=now,
    )
    authority = DelegatedAuthority(
        service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        ),
        capability=operation.capability,
        issued_at=now,
        expires_at=operation.deadline,
        request_binding=engine_request_binding(operation, request),
    )
    return operation, EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=("test:native-runtime-local-provider",),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )


def _verified(_request, candidate: str, context_digest: str):
    assert candidate.strip()
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:native-runtime-local-provider",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:native-runtime-local-provider",),
    )


async def _wait_result(service, execution_id: str):
    for _ in range(300):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("native local engine execution did not complete")


@pytest.mark.asyncio
async def test_engine_coordinator_executes_native_runtime_artifact_offline(
    tmp_path,
    monkeypatch,
) -> None:
    path, expected, _receipt = _write_native(tmp_path)
    _local_env(monkeypatch, path)
    _block_internet(monkeypatch)

    operation, command = _engine_command()
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "native-engine.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "native-submissions.sqlite3"),
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal="codedock-backend",
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                        }
                    ),
                    tenant_ids=frozenset({operation.tenant_id}),
                    capabilities=frozenset({operation.capability}),
                )
            ]
        ),
    )
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        now=operation.created_at,
    )

    registry = ProviderRegistry.from_env()
    adapter = registry.require_active()
    assert isinstance(adapter.engine.model, NativeRuntimeLocalModel)
    assert adapter.engine.model.model_digest == expected.model_digest

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified,
    )
    try:
        await coordinator.ensure_started(command)
        result = await _wait_result(
            service,
            command.execution_request.execution_id,
        )
        assert result.status == "completed"
        assert result.final_output
        assert result.provider_receipts
        assert all(
            item.startswith("provider:local:")
            for item in result.provider_receipts
        )
        assert result.verification_receipt["outcome"] == "passed"
        assert registry.require_active().model == expected.model_id
    finally:
        await coordinator.shutdown()
        service.repository.close()
        service.submissions.close()
