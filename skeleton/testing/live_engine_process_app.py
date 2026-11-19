from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

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
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.intelligence.execution_runtime import (
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import (
    ToolEffect,
    ToolExecutionRequest,
    ToolManifest,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(name + " is required")
    return value


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class _DeterministicProvider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self) -> None:
        self._responses = [
            ProviderResponse(
                text=None,
                provider=self.provider_id,
                model=self.model,
                request_id="container-provider-tool",
                response_id="container-provider-tool",
                tool_calls=(
                    ProviderToolCall(
                        call_id="container-read-call",
                        tool_id="fixture.read",
                        arguments={"key": "stage5"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=ProviderUsage(
                    input_tokens=8,
                    output_tokens=3,
                    total_tokens=11,
                    usage_source="provider",
                ),
            ),
            ProviderResponse(
                text="containerized canonical answer",
                provider=self.provider_id,
                model=self.model,
                request_id="container-provider-final",
                response_id="container-provider-final",
                finish_reason=FinishReason.COMPLETED,
                usage=ProviderUsage(
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    usage_source="provider",
                ),
            ),
        ]

    async def generate(self, _request):
        if not self._responses:
            raise AssertionError(
                "deterministic container provider received an extra turn"
            )
        return self._responses.pop(0)


class _DeterministicRegistry:
    def __init__(self, provider: _DeterministicProvider) -> None:
        self._provider = provider

    def require_active(self):
        return self._provider


def _verification(_request, candidate, _context_digest):
    if not isinstance(candidate, str) or not candidate.strip():
        raise AssertionError("container verification candidate is empty")
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "container-boundary:independent",
        },
        evidence_refs=("evidence:container-boundary",),
    )


async def _read_fixture(request: ToolExecutionRequest) -> str:
    key = str(request.arguments.get("key") or "")
    if key != "stage5":
        raise RuntimeError("unexpected deterministic fixture key")
    return "fixture:stage5:read"


def create_app() -> FastAPI:
    execution_path = Path(_required_env("TEST_ENGINE_EXECUTION_PATH"))
    submission_path = Path(_required_env("TEST_ENGINE_SUBMISSION_PATH"))
    token = _required_env("TEST_ENGINE_SERVICE_TOKEN")

    execution_path.parent.mkdir(parents=True, exist_ok=True)
    submission_path.parent.mkdir(parents=True, exist_ok=True)

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
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    service = EngineExecutionService(
        SQLiteExecutionRepository(execution_path),
        SQLiteEngineSubmissionStore(submission_path),
        authorities,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: token

    coordinator: EngineExecutionCoordinator | None = None
    tools: AsyncToolRuntime | None = None
    manifest: ToolManifest | None = None
    if _enabled("TEST_ENGINE_ENABLE_COORDINATOR"):
        tools = AsyncToolRuntime()
        manifest = ToolManifest(
            tool_id="fixture.read",
            version="1.0.0",
            description="Read deterministic Stage-5 container fixture.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                    }
                },
                "required": ["key"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
        )
        coordinator = EngineExecutionCoordinator(
            service,
            provider_registry=_DeterministicRegistry(
                _DeterministicProvider()
            ),
            tool_runtime=tools,
            verification_hook=_verification,
        )

    app.dependency_overrides[_engine_coordinator] = lambda: coordinator

    @app.on_event("startup")
    async def _startup() -> None:
        if tools is not None and manifest is not None:
            await tools.register(manifest, _read_fixture)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if coordinator is not None:
            await coordinator.shutdown()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
