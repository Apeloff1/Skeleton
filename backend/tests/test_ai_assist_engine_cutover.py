from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.engine_client import EngineClientConfig, EngineUnavailableError


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def route():
    import routes.ai as ai

    return ai


@pytest.fixture
def client(route):
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as test_client:
        yield test_client


def test_assist_executes_through_engine_and_preserves_policy_context(
    route,
    client,
    monkeypatch,
):
    captured = {}

    class FakeEngineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            captured["command"] = command
            return SimpleNamespace(
                execution_id=command.execution_request.execution_id,
                final_output="Use a guard clause.\n\n```python\nif value is None:\n    return\n```",
                verification="verification:assist",
                evidence_refs=("evidence:assist",),
            )

    fake = FakeEngineClient()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )

    response = client.post(
        "/ai/assist",
        json={
            "code": "def f(value):\n    if value is not None:\n        print(value)",
            "language": "python",
            "mode": "refactor",
            "context": "Prefer early returns.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    command = captured["command"]

    assert body["ai_generated"] is True
    assert body["provider"] == "skeleton-engine"
    assert body["model"] == "engine-routed"
    assert body["provider_request_id"] is None
    assert body["mode"] == "refactor"
    assert body["code_blocks"][0]["language"] == "python"

    assert command.operation.actor_id == "backend-ai"
    assert command.operation.tenant_id == "default"
    assert command.operation.capability == "assistant.compat"
    assert command.execution_request.context_policy["verification_profile"] == "assistant_proposal"
    assert command.delegated_authority.service_principal == "codedock-backend"
    assert command.execution_request.tool_policy["allowed_tool_ids"] == []
    assert command.compiled_context.tool_choice == "none"
    assert "def f(value)" in command.compiled_context.prompt
    assert "Prefer early returns." in command.compiled_context.prompt
    # source_snapshot intentionally binds immutable segment UUIDs, not mutable
    # human-readable source labels. Policy identity is carried by the compiled
    # instructions and the deterministic context binding.
    assert command.compiled_context.instructions == (
        route.AI_MODES["refactor"]["instruction_policy"].instructions
    )
    assert command.compiled_context.source_snapshot


def test_assist_engine_outage_returns_limited_mode_without_local_provider(
    route,
    client,
    monkeypatch,
):
    class OfflineEngineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            execution_timeout_s=5,
        )

        async def execute(self, _command):
            raise EngineUnavailableError("provider-secret-must-not-leak")

    offline = OfflineEngineClient()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: offline),
    )

    response = client.post(
        "/ai/assist",
        json={
            "code": "print('hello')",
            "language": "python",
            "mode": "explain",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_generated"] is False
    assert body["confidence"] == 0.0
    assert body["provider"] == "skeleton-engine"
    assert "engine_unavailable" in body["explanation"]
    assert "provider-secret-must-not-leak" not in response.text


def test_ai_route_source_has_no_local_provider_activation() -> None:
    source = (ROOT / "routes" / "ai.py").read_text(encoding="utf-8")

    assert "ProviderRegistry.from_env(" not in source
    assert "AI_REGISTRY" not in source
    assert "from core.ai_provider import" not in source
    assert "command_from_context" in source
    assert "EngineClient.from_env()" in source


@pytest.mark.asyncio
async def test_call_llm_preserves_requested_output_budget(route, monkeypatch) -> None:
    captured = {}

    class FakeEngineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            captured["command"] = command
            return SimpleNamespace(
                execution_id=command.execution_request.execution_id,
                final_output="bounded answer",
                verification="verification:budget",
                evidence_refs=(),
            )

    fake = FakeEngineClient()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )

    result = await route.call_llm(
        "Follow policy.",
        "Answer briefly.",
        max_output_tokens=321,
    )

    assert result["success"] is True
    command = captured["command"]
    assert command.execution_request.resource_budget["max_output_tokens"] == 321
