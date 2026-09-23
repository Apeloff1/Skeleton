from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import ai_provider
from core.ai_provider import (
    AIMessage,
    EngineProviderAdapter,
    ProviderInvocationError,
    ProviderRequest,
    ProviderUnavailableError,
)
from core.engine_client import EngineExecutionFailed


ROOT = Path(__file__).resolve().parents[1]


class FakeEngineClient:
    def __init__(self, *, result=None, failure=None):
        self.config = SimpleNamespace(
            service_principal="codedock-backend",
        )
        self.result = result or {
            "status": "completed",
            "final_output": "engine answer",
            "usage": {
                "provider_usage": [
                    {
                        "input_tokens": 11,
                        "output_tokens": 4,
                        "total_tokens": 15,
                        "cached_input_tokens": None,
                        "reasoning_tokens": None,
                        "estimated_cost": "0.01",
                        "billed_cost": None,
                        "currency": "USD",
                        "usage_source": "provider",
                    }
                ]
            },
        }
        self.failure = failure
        self.commands = []

    async def execute(self, command, *, deadline):
        self.commands.append((command, deadline))
        if self.failure is not None:
            raise self.failure
        return dict(self.result)


@pytest.mark.asyncio
async def test_engine_provider_adapter_preserves_neutral_request_contract() -> None:
    client = FakeEngineClient()
    adapter = EngineProviderAdapter(client=client)
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    request = ProviderRequest(
        instructions="system rules",
        prompt="current question",
        history=(
            AIMessage(role="user", content="older question"),
            AIMessage(role="assistant", content="older answer"),
        ),
        max_output_tokens=512,
        model="requested-model",
        tenant_id="tenant-a",
        operation_id="legacy-operation",
        estimated_cost_usd=0.01,
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        deadline=deadline,
    )

    response = await adapter.generate(request)

    assert response.text == "engine answer"
    assert response.provider == "skeleton-engine"
    assert response.model == "requested-model"
    assert response.usage.input_tokens == 11
    assert len(client.commands) == 1
    command, sent_deadline = client.commands[0]
    assert sent_deadline == deadline
    assert command.compiled_context.instructions == "system rules"
    assert command.compiled_context.prompt == "current question"
    assert command.compiled_context.history == (
        ("user", "older question"),
        ("assistant", "older answer"),
    )
    assert command.compiled_context.model == "requested-model"
    assert command.compiled_context.structured_output_schema == {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    assert command.execution_request.context_policy["handoff_digest"]


@pytest.mark.asyncio
async def test_engine_provider_adapter_redacts_engine_execution_failure() -> None:
    client = FakeEngineClient(
        failure=EngineExecutionFailed(
            "sensitive downstream detail",
            status={"failure_code": "provider_token_secret"},
        )
    )
    adapter = EngineProviderAdapter(client=client)

    with pytest.raises(
        ProviderInvocationError,
        match="model provider request failed",
    ) as excinfo:
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
            )
        )

    assert "sensitive" not in str(excinfo.value)
    assert "provider_token_secret" not in str(excinfo.value)


def test_backend_registry_from_env_constructs_engine_adapter(monkeypatch) -> None:
    adapter = EngineProviderAdapter(client=FakeEngineClient())
    monkeypatch.setattr(
        EngineProviderAdapter,
        "from_env",
        classmethod(lambda cls: adapter),
    )

    registry = ai_provider.ProviderRegistry.from_env()

    assert registry.active is adapter
    assert registry.active_id == "openai"
    assert registry.available is True


def test_backend_provider_facade_does_not_read_provider_credentials() -> None:
    source = (ROOT / "core" / "ai_provider.py").read_text(
        encoding="utf-8"
    )

    assert "OPENAI_API_KEY" not in source
    assert "EMERGENT_LLM_KEY" not in source
    assert "from openai import" not in source
    assert "import openai" not in source
    assert "EngineProviderAdapter.from_env()" in source


@pytest.mark.asyncio
async def test_engine_media_surfaces_fail_explicitly_not_locally() -> None:
    adapter = EngineProviderAdapter(client=FakeEngineClient())

    with pytest.raises(
        ProviderUnavailableError,
        match="engine media boundary",
    ):
        await adapter.generate_image(object())
