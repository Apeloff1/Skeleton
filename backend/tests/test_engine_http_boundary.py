from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    command_from_context,
)
from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


_SERVICE_TOKEN = "cross-service-engine-token-" + ("x" * 40)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="cross-service-policy",
        source_id="policy:cross-service-test",
        content="Follow the cross-service test policy.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("cross-service-test",),
        retention_class="policy",
        mandatory=True,
    )
    budget = ContextBudget(
        max_context_tokens=4096,
        reserved_output_tokens=512,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=512,
        safety_margin_tokens=128,
        max_segment_tokens=2048,
        max_artifact_tokens=1024,
        max_tool_result_tokens=1024,
    )
    digest = context_digest_payload(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        budget=budget,
        selected=(segment,),
        omitted_segment_ids=(),
        compiler_version="cross-service-v1",
    )
    return ContextEnvelope(
        context_id=str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        instruction_segments=(segment,),
        evidence_segments=(),
        tool_schema_segments=(),
        budget=budget,
        selected_tokens_estimate=segment.token_estimate,
        omitted_segment_ids=(),
        omission_reasons=(),
        source_snapshot=((segment.segment_id, segment.content_digest),),
        context_digest=digest,
        compiled_at=_now(),
        compiler_version="cross-service-v1",
    )


def _service(tmp_path) -> EngineExecutionService:
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
                    }
                ),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "http-boundary-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "http-boundary-submission.sqlite3"),
        authorities,
    )


def _app(service: EngineExecutionService) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: None
    return app


def _client(app: FastAPI) -> EngineClient:
    return EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=_SERVICE_TOKEN,
            service_principal="codedock-backend",
            request_timeout_s=2,
            execution_timeout_s=10,
        ),
        transport=httpx.ASGITransport(app=app),
    )


def _command(
    context: ContextEnvelope,
    *,
    started: datetime,
):
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="cross-service-idem",
        instructions="Follow the cross-service test policy.",
        prompt="Return a bounded answer.",
        objective="Cross-service engine boundary test",
        verification_profile="assistant_proposal",
        service_principal="codedock-backend",
        created_at=started,
        deadline=started + timedelta(seconds=10),
        trace_id="trace-cross-service",
        max_model_turns=2,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
    )


@pytest.mark.asyncio
async def test_backend_client_crosses_authenticated_engine_boundary_idempotently(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    client = _client(app)
    context = _context()

    first_started = _now()
    first = _command(context, started=first_started)
    ack = await client.submit(first)

    assert ack["operation_id"] == context.operation_id
    assert ack["execution_id"] == context.execution_id
    assert ack["state"] == "admitted"
    accepted_at = ack["accepted_at"]

    retry = _command(
        context,
        started=first_started + timedelta(seconds=1),
    )
    assert retry.command_digest != first.command_digest
    assert retry.submission_digest == first.submission_digest

    replay = await client.submit(retry)
    assert replay["operation_id"] == ack["operation_id"]
    assert replay["execution_id"] == ack["execution_id"]
    assert replay["idempotency_digest"] == ack["idempotency_digest"]
    assert replay["accepted_at"] == accepted_at

    status = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id="trace-status",
    )
    assert status["operation_id"] == context.operation_id
    assert status["execution_id"] == context.execution_id
    assert status["execution_state"] == "admitted"
    assert status["cancellation_requested"] is False

    with pytest.raises(EngineAuthorizationError):
        await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-b",
        )

    cancelled = await client.cancel(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="cross-service cancellation test",
        trace_id="trace-cancel",
    )
    assert cancelled["operation_id"] == context.operation_id
    assert cancelled["execution_id"] == context.execution_id
    assert cancelled["cancellation_requested"] is True

    after = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )
    assert after["cancellation_requested"] is True


@pytest.mark.asyncio
async def test_cross_service_principal_and_capability_denials_are_403_classified(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    context = _context()
    command = _command(context, started=_now())

    wrong_principal = EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=_SERVICE_TOKEN,
            service_principal="untrusted-service",
        ),
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(EngineAuthorizationError):
        await wrong_principal.submit(command)

    # A valid principal may not submit a capability outside its server-side grant.
    admin_command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.compat",
        idempotency_key="wrong-capability",
        instructions="Policy.",
        prompt="Prompt.",
        verification_profile="assistant_proposal",
        service_principal="codedock-backend",
        created_at=_now(),
        deadline=_now() + timedelta(seconds=10),
    )
    with pytest.raises(EngineAuthorizationError):
        await _client(app).submit(admin_command)
