from __future__ import annotations

import asyncio

from fastapi import FastAPI
import httpx
import pytest

from core.engine_client import EngineClient, EngineClientConfig
from core.engine_text import EngineTextError, EngineTextRequest, execute_engine_text
from skeleton.api.engine_authority import EngineAuthorityRegistry, EngineServiceGrant
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import EngineExecutionService, SQLiteEngineSubmissionStore
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import (
    FinishReason,
    ProviderResponse,
    ProviderUsage,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime


_SERVICE_TOKEN = "cross-service-engine-token-" + ("x" * 40)


class _Provider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self, *, text: str = "engine answer", gate: asyncio.Event | None = None) -> None:
        self.text = text
        self.gate = gate
        self.started = asyncio.Event()
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        return ProviderResponse(
            text=self.text,
            provider=self.provider_id,
            model=self.model,
            request_id="provider-request",
            response_id="provider-response",
            finish_reason=FinishReason.COMPLETED,
            usage=ProviderUsage(
                input_tokens=8,
                output_tokens=4,
                total_tokens=12,
                usage_source="provider",
            ),
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


class _Registry:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    def require_active(self):
        return self.provider


def _service(tmp_path, *, tenant_ids=frozenset({"tenant-a"}), scopes=None):
    if scopes is None:
        scopes = frozenset(
            {
                "engine:submit",
                "engine:read",
                "engine:cancel",
                "engine:events",
            }
        )
    authority = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="codedock-backend",
                scopes=frozenset(scopes),
                tenant_ids=frozenset(tenant_ids),
                capabilities=frozenset({"assistant.compat"}),
            )
        ]
    )
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "cross-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "cross-submission.sqlite3"),
        authority,
    )


def _app(service, coordinator) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: coordinator
    return app


def _client(app: FastAPI) -> EngineClient:
    return EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=_SERVICE_TOKEN,
            service_principal="codedock-backend",
            request_timeout_s=2.0,
            poll_interval_s=0.001,
            execution_timeout_s=5.0,
            max_poll_attempts=10_000,
        ),
        transport=httpx.ASGITransport(app=app),
    )


def _request(*, tenant_id: str = "tenant-a", key: str = "cross-idem") -> EngineTextRequest:
    return EngineTextRequest(
        instructions="Respond with a bounded assistant proposal.",
        prompt="Give one deterministic answer.",
        idempotency_key=key,
        tenant_id=tenant_id,
        actor_id="backend-ai",
        capability="assistant.compat",
        verification_profile="assistant_proposal",
        max_output_tokens=512,
    )


@pytest.mark.asyncio
async def test_cross_service_golden_journey_and_retry_are_single_execution(tmp_path) -> None:
    service = _service(tmp_path)
    provider = _Provider()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
    )
    client = _client(_app(service, coordinator))
    request = _request()

    first = await execute_engine_text(request, client=client)
    second = await execute_engine_text(request, client=client)

    assert first.text == "engine answer"
    assert second.text == "engine answer"
    assert first.execution_id == second.execution_id
    assert len(provider.requests) == 1

    provider_request = provider.requests[0]
    assert provider_request.operation_id is not None
    assert provider_request.execution_id == first.execution_id
    assert provider_request.context_id is not None
    assert provider_request.context_digest is not None
    assert provider_request.context_source_snapshot
    assert provider_request.context_compiler_version

    status = await client.status(
        first.execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
    )
    assert status["execution_state"] == "completed"
    assert status["operation_state"] == "completed"
    assert status["result_ref"] == "execution-result:" + first.execution_id

    events = await client.events(
        first.execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
    )
    result_events = [
        event
        for event in events["events"]
        if event.get("type") == "execution.result"
    ]
    assert len(result_events) == 1
    result = result_events[0]["result"]
    assert result["status"] == "completed"
    assert result["final_output"] == "engine answer"
    assert result["verification_receipt"]["verification_profile"] == "assistant_proposal"
    assert result["verification_receipt"]["claim_kind"] == "hypothesis"
    assert result["provider_receipts"]

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_tenant_and_scope_denial_never_reach_provider(tmp_path) -> None:
    provider = _Provider()
    tenant_service = _service(tmp_path, tenant_ids=frozenset({"tenant-a"}))
    tenant_coordinator = EngineExecutionCoordinator(
        tenant_service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
    )
    tenant_client = _client(_app(tenant_service, tenant_coordinator))

    with pytest.raises(EngineTextError, match="canonical engine text execution failed"):
        await execute_engine_text(
            _request(tenant_id="tenant-b", key="tenant-denied"),
            client=tenant_client,
        )
    assert provider.requests == []
    await tenant_coordinator.shutdown()

    scoped_provider = _Provider()
    scoped_service = _service(
        tmp_path,
        scopes=frozenset({"engine:read", "engine:cancel", "engine:events"}),
    )
    scoped_coordinator = EngineExecutionCoordinator(
        scoped_service,
        provider_registry=_Registry(scoped_provider),
        tool_runtime=AsyncToolRuntime(),
    )
    scoped_client = _client(_app(scoped_service, scoped_coordinator))

    with pytest.raises(EngineTextError, match="canonical engine text execution failed"):
        await execute_engine_text(
            _request(key="scope-denied"),
            client=scoped_client,
        )
    assert scoped_provider.requests == []
    await scoped_coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_cancel_fences_late_provider_result(tmp_path) -> None:
    gate = asyncio.Event()
    provider = _Provider(text="late answer must not win", gate=gate)
    service = _service(tmp_path)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
    )
    client = _client(_app(service, coordinator))
    request = _request(key="cancel-late")

    execution_task = asyncio.create_task(
        execute_engine_text(request, client=client)
    )
    await asyncio.wait_for(provider.started.wait(), timeout=2.0)
    execution_id = provider.requests[0].execution_id
    assert execution_id is not None

    first_cancel = await client.cancel(
        execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
        reason="user requested cancellation",
    )
    second_cancel = await client.cancel(
        execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
        reason="retry cancellation",
    )
    assert first_cancel["cancellation_requested"] is True
    assert second_cancel["cancellation_requested"] is True

    gate.set()
    with pytest.raises(EngineTextError, match="canonical engine text execution failed"):
        await execution_task

    status = await client.status(
        execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
    )
    assert status["execution_state"] == "cancelled"
    assert status["operation_state"] == "cancelled"
    assert status["cancellation_requested"] is True

    events = await client.events(
        execution_id,
        actor_id="backend-ai",
        tenant_id="tenant-a",
    )
    result_events = [
        event
        for event in events["events"]
        if event.get("type") == "execution.result"
    ]
    assert len(result_events) == 1
    assert result_events[0]["result"]["status"] == "cancelled"
    assert result_events[0]["result"]["final_output"] is None
    assert (
        result_events[0]["result"]["usage"]["error_code"]
        == "cancellation_requested"
    )

    await coordinator.shutdown()
