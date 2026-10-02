from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import socket
from uuid import uuid4

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
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
from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _verified_execution(
    _request: AIExecutionRequest,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "local-engine:independent-structural",
            "candidate_digest": hashlib.sha256(
                candidate.encode("utf-8")
            ).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:local-engine-completion",),
    )


def _write_model_artifact(path) -> ReferenceNGramModel:
    model = ReferenceNGramModel.train(
        [
            "two plus two four",
            "two plus two four",
            "two plus two four",
            "two plus two four",
            "three plus three six",
        ],
        order=2,
    )
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
    return model


def _service(tmp_path) -> EngineExecutionService:
    repository = SQLiteExecutionRepository(
        tmp_path / "engine-execution.sqlite3"
    )
    submissions = SQLiteEngineSubmissionStore(
        tmp_path / "engine-submissions.sqlite3"
    )
    authorities = EngineAuthorityRegistry(
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
                tenant_ids=frozenset({"tenant-local"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    return EngineExecutionService(
        repository,
        submissions,
        authorities,
    )


def _command() -> EngineExecutionCommand:
    now = datetime.now(timezone.utc)
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-local",
        actor_id="local-operator",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key="local-engine-completion",
        trace_id="trace-local-engine-completion",
    )
    execution_id = "local-engine-" + str(uuid4())
    context_id = str(uuid4())
    turn_id = str(uuid4())
    segment_id = str(uuid4())
    snapshot = ((segment_id, "a" * 64),)
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=operation.tenant_id,
        context_id=context_id,
        context_digest="b" * 64,
        compiler_version="local-engine-test",
        source_snapshot=snapshot,
        data_class="internal",
        instructions="Answer using the activated local model only.",
        prompt="two plus two",
    )
    execution_request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="Answer locally without hosted-provider I/O.",
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "source_snapshot": [
                [segment, digest]
                for segment, digest in handoff.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 1,
            "max_output_tokens": 8,
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
        request_binding=engine_request_binding(
            operation,
            execution_request,
        ),
    )
    return EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=("context-segment:" + segment_id,),
        resource_budget=dict(execution_request.resource_budget),
        stream_preferences={"mode": "events"},
    )


async def _wait_for_result(
    service: EngineExecutionService,
    execution_id: str,
):
    for _ in range(500):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("local engine execution did not terminate")


@pytest.mark.asyncio
async def test_real_engine_coordinator_executes_local_artifact_without_network_or_credentials(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "local-model.json"
    model = _write_model_artifact(artifact)

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(artifact))
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError(
                "assembled local engine attempted provider network I/O"
            )
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)

    registry = ProviderRegistry.from_env()
    active = registry.require_active()
    assert active.provider_id == "local"
    assert active.model == model.model_id
    status = registry.statuses()[0]
    assert status["available"] is True
    assert status["execution_mode"] == "local"
    assert status["network_policy"] == "none"
    assert status["artifact"]["model_digest"] == model.model_digest

    service = _service(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
        now=command.operation.created_at,
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    result = await _wait_for_result(
        service,
        command.execution_request.execution_id,
    )

    assert result.status == "completed"
    assert result.final_output is not None
    assert result.final_output.split()[0] == "four"
    assert result.provider_receipts
    assert all(
        receipt.startswith("provider:local:")
        for receipt in result.provider_receipts
    )
    assert result.evidence_refs == ("evidence:local-engine-completion",)
    assert result.stream_terminal_event is not None
    assert service.repository.result(result.execution_id) == result


def test_local_engine_mode_requires_valid_content_addressed_artifact(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "bad-model.json"
    model = _write_model_artifact(artifact)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["model_digest"] = "0" * 64
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(artifact))
    monkeypatch.delenv("AI_SECONDARY_API_KEY", raising=False)
    monkeypatch.delenv("AI_SECONDARY_BASE_URL", raising=False)
    monkeypatch.delenv("AI_SECONDARY_MODEL", raising=False)
    monkeypatch.delenv("AI_VERIFICATION_MODEL", raising=False)

    with pytest.raises(
        ProviderUnavailableError,
        match="artifact is unavailable or invalid",
    ):
        ProviderRegistry.from_env()

    assert model.model_digest != "0" * 64


def test_local_engine_mode_rejects_external_failover_configuration(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "local-model.json"
    _write_model_artifact(artifact)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(artifact))
    monkeypatch.setenv("AI_SECONDARY_API_KEY", "external-secret")
    monkeypatch.setenv("AI_SECONDARY_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SECONDARY_MODEL", "external-model")

    with pytest.raises(
        ProviderUnavailableError,
        match="not allowed when AI_PROVIDER=local",
    ):
        ProviderRegistry.from_env()
