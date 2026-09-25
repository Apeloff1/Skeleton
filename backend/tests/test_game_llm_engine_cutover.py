from __future__ import annotations

from pathlib import Path

import pytest

from core.engine_client import EngineClientConfig
from core.engine_text import EngineTextError, EngineTextResponse
from services import game_llm_service


ROOT = Path(__file__).resolve().parents[1]


def _engine_response(text: str = "game answer") -> EngineTextResponse:
    return EngineTextResponse(
        text=text,
        execution_id="game-exec",
        verification="verification:game",
        evidence_refs=(),
        usage={"model_turns": 1, "tool_calls": 0},
    )


@pytest.mark.asyncio
async def test_game_llm_generate_delegates_to_engine_without_provider_pin(
    monkeypatch,
) -> None:
    captured = []

    async def execute(request):
        captured.append(request)
        return _engine_response()

    fake_client = type(
        "ConfiguredEngine",
        (),
        {
            "config": EngineClientConfig(
                base_url="http://skeleton:8001",
                execution_timeout_s=5,
            )
        },
    )()
    monkeypatch.setattr(
        game_llm_service.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake_client),
    )
    monkeypatch.setattr(
        game_llm_service.outcalls,
        "is_internal",
        lambda: False,
    )

    service = game_llm_service.GameLLMService(
        model="legacy-model",
        provider="legacy-provider",
        engine_executor=execute,
    )
    result = await service.generate(
        "Build safe deterministic game logic.",
        "Create one NPC.",
        session_id="session-a",
        rag_topic="",
    )

    assert result["success"] is True
    assert result["response"] == "game answer"
    assert result["provider"] == "skeleton-engine"
    assert result["model"] == "engine-routed"
    assert result["fallback"] is False
    assert len(captured) == 1
    request = captured[0]
    assert request.actor_id == "game-llm-service"
    assert request.capability == "assistant.compat"
    assert request.max_output_tokens == 16_384
    assert request.instructions == "Build safe deterministic game logic."
    assert request.prompt == "Create one NPC."
    assert not hasattr(request, "provider")
    assert not hasattr(request, "model")


@pytest.mark.asyncio
async def test_game_llm_engine_failure_is_bounded_and_generic(
    monkeypatch,
) -> None:
    async def execute(_request):
        raise EngineTextError("secret-upstream-detail")

    fake_client = type(
        "ConfiguredEngine",
        (),
        {
            "config": EngineClientConfig(
                base_url="http://skeleton:8001",
                execution_timeout_s=5,
            )
        },
    )()
    monkeypatch.setattr(
        game_llm_service.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake_client),
    )
    monkeypatch.setattr(
        game_llm_service.outcalls,
        "is_internal",
        lambda: False,
    )

    service = game_llm_service.GameLLMService(
        engine_executor=execute,
    )
    result = await service.generate(
        "Rules",
        "Prompt",
        rag_topic="",
    )

    assert result["success"] is False
    assert result["error_code"] == "engine_failure"
    assert result["provider"] == "skeleton-engine"
    assert "secret-upstream-detail" not in str(result)


def test_game_llm_status_reports_engine_ownership(monkeypatch) -> None:
    fake_client = type(
        "ConfiguredEngine",
        (),
        {
            "config": EngineClientConfig(
                base_url="http://skeleton:8001",
                execution_timeout_s=5,
            )
        },
    )()
    monkeypatch.setattr(
        game_llm_service.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake_client),
    )

    service = game_llm_service.GameLLMService(
        model="legacy-model",
        provider="openai",
    )
    status = service.provider_status()

    assert service.available is True
    assert service.api_key == "configured"
    assert status["requested_provider"] == "openai"
    assert status["requested_model"] == "legacy-model"
    assert status["active_provider"] == "skeleton-engine"
    assert status["active_model"] == "engine-routed"


def test_game_llm_source_has_no_local_provider_activation() -> None:
    source = (
        ROOT / "services" / "game_llm_service.py"
    ).read_text(encoding="utf-8")

    assert "ProviderRegistry.from_env(" not in source
    assert "ProviderRequest(" not in source
    assert "from core.ai_provider import" not in source
    assert "execute_engine_text" in source
