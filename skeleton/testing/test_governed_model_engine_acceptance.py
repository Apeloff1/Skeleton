"""Observed licensed training produces the model served by the sealed engine."""

from __future__ import annotations

import asyncio
import hashlib
import socket
import threading
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from fastapi import FastAPI

from backend.core.engine_client import (
    EngineClient,
    EngineClientConfig,
    EngineExecutionFailed,
)
from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    load_local_model_artifact,
)
from skeleton.ai.runtime.training.cli import build_governed_artifact
from skeleton.ai.runtime.training.control import TrainingRepository
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
)
from skeleton.api.engine_routes import (
    router as engine_router,
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
from skeleton.intelligence.execution_runtime import (
    ExecutionVerificationDecision,
    _provider_response_binding,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRegistry
from skeleton.skills.tool_runtime import AsyncToolRuntime

_PRINCIPAL = "codedock-backend"
_TENANT = "tenant-governed-local"
_SCOPES = (
    "engine:submit",
    "engine:read",
    "engine:cancel",
    "engine:events",
    "engine:approve",
)


def _offline(monkeypatch):
    original = socket.socket

    def socket_without_internet(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("governed local model attempted Internet I/O")
        return original(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", socket_without_internet)


@pytest.fixture(params=("reference", "neural", "data_parallel"))
def governed_artifact(request, tmp_path, monkeypatch):
    algorithm = request.param
    if algorithm != "reference":
        pytest.importorskip("numpy")
    _offline(monkeypatch)
    corpus = "a" * 16 if algorithm != "reference" else "local engine answer complete"
    source = tmp_path / "licensed-corpus.txt"
    source.write_text(corpus, encoding="utf-8")
    arguments = {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "training-state",
        "output_path": tmp_path / "trained-model.json",
        "run_id": "engine-build-" + algorithm,
        "dataset_id": "licensed-engine-corpus",
        "rights_refs": ("license:operator-owned-engine-acceptance",),
        "algorithm": algorithm,
        "classification": "internal",
        "hidden_size": 4,
        "epochs": 8,
        "learning_rate": 1.0,
        "order": 2,
        "seed": 0,
        "max_steps": 256,
        "max_updates": 16,
        "max_training_bytes": 4096,
    }
    receipt = build_governed_artifact(**arguments)
    artifact = load_local_model_artifact(arguments["output_path"])
    assert artifact.model.model_digest == receipt["model_digest"]
    assert artifact.receipt.artifact_sha256 == receipt["artifact"]["artifact_sha256"]

    # Read reopened authorities rather than relying on the builder's live objects.
    datasets = DatasetRegistry(Path(arguments["state_directory"]) / "datasets.sqlite3")
    runs = TrainingRepository(Path(arguments["state_directory"]) / "training.sqlite3")
    try:
        manifest = datasets.dataset(receipt["dataset_digest"])
        assert manifest.classification == "internal"
        assert {"training", "evaluation"} <= set(manifest.permitted_uses)
        materialized = datasets.materialized_sources(receipt["dataset_digest"])
        assert len(materialized) == 1
        assert materialized[0].payload == source.read_bytes()
        assert materialized[0].rights_refs == arguments["rights_refs"]
        assert datasets.training_corpus(manifest.digest) == (corpus,)
        assert runs.state(arguments["run_id"]) == "completed"
        assert runs.latest_checkpoint(arguments["run_id"]).digest == receipt["checkpoint_digest"]
    finally:
        datasets.close()
        runs.close()

    # Artifact publication can be retried after a process restart without SGD replay.
    arguments["output_path"].unlink()
    update = (
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document"
        if algorithm != "reference"
        else "skeleton.ai.runtime.training.trainer.ReferenceNGramModel.train"
    )
    with patch(update, side_effect=AssertionError("committed training was replayed")):
        assert build_governed_artifact(**arguments) == receipt
    assert load_local_model_artifact(arguments["output_path"]).receipt == artifact.receipt
    if algorithm != "reference":
        assert receipt["final_loss"] < receipt["initial_loss"]
        assert receipt["update_count"] == 8

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(arguments["output_path"]))
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "0")
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "8")
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    return algorithm, receipt


def _command(algorithm):
    now = datetime.now(UTC)
    operation = OperationEnvelope(
        operation_id=str(uuid5(NAMESPACE_URL, "governed-engine-operation:" + algorithm)),
        tenant_id=_TENANT,
        actor_id="licensed-model-operator",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=1),
        idempotency_key="governed-local-" + str(uuid4()),
        trace_id="trace-governed-model",
    )
    # The canonical local adapter derives its sampling seed from execution
    # identity. Stable fixture IDs make neural expectations reproducible.
    execution_id = str(uuid5(NAMESPACE_URL, "governed-engine-execution:" + algorithm))
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=str(uuid4()),
        tenant_id=operation.tenant_id,
        context_id=str(uuid4()),
        context_digest="a" * 64,
        compiler_version="governed-model-acceptance@1",
        source_snapshot=((str(uuid4()), "b" * 64),),
        data_class="internal",
        instructions="Complete the prompt from the activated local model.",
        prompt="a" if algorithm != "reference" else "local engine",
        purpose="model-inference",
        history=(),
    )
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="Serve the artifact produced by licensed durable training.",
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
            "max_output_tokens": 1 if algorithm != "reference" else 8,
        },
        stop_policy={
            "deadline": operation.deadline.isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=now,
    )
    authority = DelegatedAuthority(
        service_principal=_PRINCIPAL,
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=_SCOPES,
        capability=operation.capability,
        issued_at=now,
        expires_at=operation.deadline,
        request_binding=engine_request_binding(operation, request),
    )
    return EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=("evidence:licensed-local-model",),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )


def _assert_output(algorithm, candidate):
    if algorithm == "reference":
        assert candidate == "answer complete"
    else:
        assert candidate and set(candidate) == {"a"}


@asynccontextmanager
async def _engine_stack(tmp_path, algorithm):
    def verify(_request, candidate, context_digest):
        _assert_output(algorithm, candidate)
        return ExecutionVerificationDecision(
            passed=True,
            receipt={
                "outcome": "passed",
                "policy_satisfied": True,
                "verifier_id": "test:governed-model-engine",
                "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
                "context_digest": context_digest,
            },
            evidence_refs=("evidence:actual-local-model-output",),
        )

    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "engine.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submissions.sqlite3"),
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal=_PRINCIPAL,
                    scopes=frozenset(_SCOPES),
                    tenant_ids=frozenset({_TENANT}),
                    capabilities=frozenset({"assistant.chat"}),
                )
            ]
        ),
    )
    registry = ProviderRegistry.from_env()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=registry,
        tool_runtime=AsyncToolRuntime(),
        verification_hook=verify,
    )
    app = FastAPI()
    app.include_router(engine_router, prefix="/api/v1")
    token = "governed-local-engine-" + "x" * 40
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_coordinator] = lambda: coordinator
    app.dependency_overrides[_engine_service_token] = lambda: token
    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton.test",
            service_token=token,
            service_principal=_PRINCIPAL,
            request_timeout_s=2,
            poll_interval_s=0.001,
            execution_timeout_s=5,
        ),
        transport=httpx.ASGITransport(app=app),
    )
    try:
        yield client, service, registry, app
    finally:
        await coordinator.shutdown()
        service.repository.close()
        service.submissions.close()


@pytest.mark.asyncio
async def test_governed_training_artifact_served_by_authenticated_engine_and_reopened(
    tmp_path, monkeypatch, governed_artifact
):
    algorithm, build = governed_artifact
    command = _command(algorithm)
    responses = []
    async with _engine_stack(tmp_path, algorithm) as (client, service, registry, app):
        adapter = registry.require_active()
        generate = adapter.generate

        async def observe_actual_generate(request):
            response = await generate(request)
            responses.append(response)
            return response

        monkeypatch.setattr(adapter, "generate", observe_actual_generate)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://skeleton.test"
        ) as unauthorized:
            denied = await unauthorized.post(
                "/api/v1/engine/executions",
                json={
                    "actor_id": command.operation.actor_id,
                    "tenant_id": command.operation.tenant_id,
                    "command": command.as_dict(),
                },
            )
        assert denied.status_code == 401
        assert service.submissions.get_by_execution_id(command.execution_request.execution_id) is None
        assert responses == []

        result = await client.execute(command)
        assert result.status == "completed"
        _assert_output(algorithm, result.final_output)
        assert len(responses) == 1
        response = responses[0]
        assert response.text == result.final_output
        assert response.provider == "local"
        assert response.model == adapter.model
        assert adapter.engine.model.model_digest == build["model_digest"]
        assert response.governance_decision_id
        assert response.admission_decision_id
        assert response.data_class == "internal"
        assert response.context_digest == command.compiled_context.context_digest
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
        assert response.usage.billed_cost == "0"
        assert response.usage.usage_source == "local_model"
        assert result.usage["provider_usage"] == [response.usage.as_dict()]
        assert result.usage["model_turns"] == 1
        assert result.usage["tool_calls"] == 0
        assert result.verification_receipt["outcome"] == "passed"

        checkpoint = service.repository.latest_checkpoint(result.execution_id)
        payload = checkpoint.payload
        turn_id = payload["last_provider"]["turn_id"]
        reference, fingerprint = _provider_response_binding(response, turn_id)
        assert tuple(result.provider_receipts) == (reference,)
        assert reference.startswith("provider:local:")
        assert payload["provider_response_bindings"] == {reference: fingerprint}
        assert payload["usage_events"] == [response.usage.as_dict()]
        # Both policy receipts are covered by the durable normalized response hash.
        for field in ("governance_decision_id", "admission_decision_id"):
            assert _provider_response_binding(replace(response, **{field: None}), turn_id)[1] != fingerprint

        inventory = await client.provider_status(trace_id=command.operation.trace_id)
        assert inventory["active"] == "local"
        assert inventory["available"] is True
        assert len(inventory["providers"]) == 1
        status = inventory["providers"][0]
        assert status["id"] == "local"
        assert status["network_policy"] == "none"
        assert status["artifact"]["model_digest"] == build["model_digest"]
        assert status["artifact"]["artifact_sha256"] == build["artifact"]["artifact_sha256"]
        assert status["architecture_acknowledged"] is True
        assert registry.architecture_receipt()["provider_id"] == "local"
        events = await client.events(
            result.execution_id,
            actor_id=command.operation.actor_id,
            tenant_id=command.operation.tenant_id,
            trace_id=command.operation.trace_id,
        )
        assert any(event.get("type") == "execution.result" for event in events["events"])

    # A new registry, coordinator and reopened durable engine return the result.
    async with _engine_stack(tmp_path, algorithm) as (client, service, registry, _app):

        async def no_replay(_request):
            raise AssertionError("completed engine execution dispatched the model again")

        monkeypatch.setattr(registry.require_active(), "generate", no_replay)
        retry = await client.execute(command)
        assert retry == result
        assert service.repository.latest_checkpoint(result.execution_id).payload == payload


@pytest.mark.asyncio
async def test_governed_local_engine_http_cancel_interrupts_inference_without_hosted_fallback(
    tmp_path, monkeypatch, governed_artifact
):
    algorithm, _build = governed_artifact
    command = _command(algorithm)
    entered = threading.Event()
    cancelled = threading.Event()
    release = threading.Event()
    calls = []
    async with _engine_stack(tmp_path, algorithm) as (client, service, registry, _app):

        def bounded_infer(request, cancellation):
            calls.append(request)
            entered.set()
            while not cancellation.wait(0.01):
                if release.is_set():
                    raise LocalInferenceCancelled("test cleanup")
            cancelled.set()
            raise LocalInferenceCancelled("authorized engine HTTP cancellation")

        monkeypatch.setattr(registry.require_active().engine.model, "infer", bounded_infer)
        execution = asyncio.create_task(client.execute(command))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            status = await client.cancel(
                command.execution_request.execution_id,
                actor_id=command.operation.actor_id,
                tenant_id=command.operation.tenant_id,
                reason="operator cancels the activated local model",
                trace_id=command.operation.trace_id,
            )
            assert status["cancellation_requested"] is True
            with pytest.raises(EngineExecutionFailed) as failed:
                await asyncio.wait_for(execution, timeout=3)
            failure = failed.value
            assert failure.status == "cancelled"
            assert failure.failure_code == "cancellation_requested"
            assert failure.result == service.repository.result(failure.execution_id).as_dict()
            result = service.repository.result(failure.execution_id)
            assert cancelled.is_set()
            assert len(calls) == 1
            assert result.status == "cancelled"
            assert result.final_output is None
            assert result.usage["error_code"] == "cancellation_requested"
            assert result.provider_receipts == ()
            assert service.repository.get(result.execution_id).cancellation_requested
            inventory = await client.provider_status()
            assert inventory["active"] == "local"
            assert [item["id"] for item in inventory["providers"]] == ["local"]
        finally:
            release.set()
            if not execution.done():
                execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
