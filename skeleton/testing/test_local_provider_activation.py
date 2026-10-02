from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import socket
import threading
from uuid import uuid4

import pytest

from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    LocalModelArtifactError,
    ReferenceNGramModel,
    load_local_model_artifact,
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
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import (
    ProviderRegistry,
    ProviderUnavailableError,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _write_model(tmp_path):
    model = ReferenceNGramModel.train(
        [
            "local engine answer complete",
            "local engine answer complete",
            "local engine answer complete",
        ],
        order=2,
        model_id="assembled-local-reference",
    )
    path = tmp_path / "local-model.json"
    path.write_text(
        json.dumps(
            model.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path, model


def _local_env(monkeypatch, path) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "8")
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "17")
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def _block_internet(monkeypatch):
    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("local provider attempted Internet socket I/O")
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)


def test_local_model_artifact_receipt_binds_exact_file_and_model(tmp_path) -> None:
    path, expected = _write_model(tmp_path)

    loaded = load_local_model_artifact(path)

    assert loaded.model.model_id == expected.model_id
    assert loaded.model.model_digest == expected.model_digest
    assert loaded.receipt.model_digest == expected.model_digest
    assert loaded.receipt.artifact_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.receipt.reference.startswith("local-model-artifact:")
    assert loaded.receipt.schema == "reference_ngram"


def test_local_model_artifact_rejects_duplicate_keys_and_digest_drift(tmp_path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"kind":"reference_ngram","kind":"reference_ngram"}',
        encoding="utf-8",
    )
    with pytest.raises(LocalModelArtifactError, match="duplicate JSON key"):
        load_local_model_artifact(duplicate)

    path, _ = _write_model(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["model_digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalModelArtifactError, match="artifact is invalid"):
        load_local_model_artifact(path)


@pytest.mark.asyncio
async def test_provider_registry_local_mode_is_credential_free_and_network_free(
    tmp_path,
    monkeypatch,
) -> None:
    path, expected = _write_model(tmp_path)
    _local_env(monkeypatch, path)
    _block_internet(monkeypatch)

    registry = ProviderRegistry.from_env()
    adapter = registry.require_active()
    status = registry.statuses()

    assert adapter.provider_id == "local"
    assert adapter.model == expected.model_id
    assert registry.active_id == "local"
    assert registry.available is True
    assert len(status) == 1
    assert status[0]["id"] == "local"
    assert status[0]["network_policy"] == "none"
    assert status[0]["artifact"]["model_digest"] == expected.model_digest
    assert status[0]["architecture_acknowledged"] is True

    from skeleton.provider_runtime import ProviderRequest

    response = await adapter.generate(
        ProviderRequest(
            instructions="Answer from the activated local artifact.",
            prompt="local engine",
            max_output_tokens=8,
        )
    )
    assert response.provider == "local"
    assert response.model == expected.model_id
    assert response.usage.billed_cost == "0"
    assert response.usage.usage_source == "local_model"


@pytest.mark.parametrize(
    ("name", "value", "match"),
    [
        (
            "AI_SECONDARY_API_KEY",
            "external-key",
            "secondary external provider",
        ),
        (
            "AI_VERIFICATION_MODEL",
            "external-verifier",
            "semantic verifier",
        ),
    ],
)
def test_local_mode_rejects_external_provider_escape_configuration(
    tmp_path,
    monkeypatch,
    name,
    value,
    match,
) -> None:
    path, _ = _write_model(tmp_path)
    _local_env(monkeypatch, path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ProviderUnavailableError, match=match):
        ProviderRegistry.from_env()


def _verified(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    assert candidate.strip()
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:assembled-local-engine",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:assembled-local-engine",),
    )


def _engine_bundle():
    now = datetime.now(timezone.utc)
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-local",
        actor_id="operator-local",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=2),
        idempotency_key="assembled-local-idem",
        trace_id="trace-assembled-local",
    )
    execution_id = str(uuid4())
    context_id = str(uuid4())
    turn_id = str(uuid4())
    segment_id = str(uuid4())
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=operation.tenant_id,
        context_id=context_id,
        context_digest="a" * 64,
        compiler_version="test-local-engine-compiler",
        source_snapshot=((segment_id, "b" * 64),),
        data_class="internal",
        instructions="Answer only through the activated local model.",
        prompt="local engine",
        purpose="model-inference",
        history=(),
    )
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="Prove the assembled engine can execute locally.",
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "source_snapshot": [
                [item[0], item[1]] for item in handoff.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "data_class": "internal",
            "purpose": "tool-execution",
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 4,
            "max_output_tokens": 32,
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
    command = EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=("test:assembled-local",),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )
    return operation, command


async def _wait_result(service, execution_id: str):
    for _ in range(200):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("local engine execution did not complete")


@pytest.mark.asyncio
async def test_engine_coordinator_executes_local_registry_without_hosted_provider(
    tmp_path,
    monkeypatch,
) -> None:
    path, expected = _write_model(tmp_path)
    _local_env(monkeypatch, path)
    _block_internet(monkeypatch)

    operation, command = _engine_bundle()
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "engine-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "engine-submissions.sqlite3"),
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
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified,
    )

    await coordinator.ensure_started(command)
    result = await _wait_result(
        service,
        command.execution_request.execution_id,
    )

    assert result.status == "completed"
    assert result.final_output
    assert result.provider_receipts
    assert all(item.startswith("provider:local:") for item in result.provider_receipts)
    assert result.verification_receipt["outcome"] == "passed"
    assert registry.require_active().model == expected.model_id

    await coordinator.shutdown()
    service.repository.close()
    service.submissions.close()


@pytest.mark.asyncio
async def test_engine_coordinator_interrupts_running_local_inference_and_finalizes_cancelled(
    tmp_path,
    monkeypatch,
) -> None:
    path, _expected = _write_model(tmp_path)
    _local_env(monkeypatch, path)
    _block_internet(monkeypatch)

    operation, command = _engine_bundle()
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "cancel-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "cancel-submissions.sqlite3"),
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
    entered = threading.Event()
    cancel_seen = threading.Event()
    calls = 0

    def blocking_infer(request, cancel):
        nonlocal calls
        calls += 1
        entered.set()
        while not cancel.wait(0.01):
            pass
        cancel_seen.set()
        raise LocalInferenceCancelled("engine-local inference cancelled")

    monkeypatch.setattr(adapter.engine.model, "infer", blocking_infer)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified,
    )

    await coordinator.ensure_started(command)
    assert await asyncio.to_thread(entered.wait, 2.0)

    status = service.cancel(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        now=operation.created_at + timedelta(seconds=1),
    )
    assert status.cancellation_requested is True

    await coordinator.interrupt_cancelled_execution(
        command.execution_request.execution_id
    )
    result = await _wait_result(
        service,
        command.execution_request.execution_id,
    )

    assert cancel_seen.is_set()
    assert calls == 1
    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.usage["error_code"] == "cancellation_requested"

    status = service.status(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
    )
    assert status.execution_state == "cancelled"
    assert status.result is not None
    assert status.result["status"] == "cancelled"

    await coordinator.shutdown()
    service.repository.close()
    service.submissions.close()
