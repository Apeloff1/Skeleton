from __future__ import annotations

import pytest

from core.ai_provider_compat import ChatResponse, LlmChat, UserMessage
from core.engine_text import EngineTextError, EngineTextResponse
from skeleton.provider_runtime import ProviderUnavailableError


def _response(text: str = "answer") -> EngineTextResponse:
    return EngineTextResponse(
        text=text,
        execution_id="exec-compat",
        verification="verification:compat",
        evidence_refs=(),
        usage={"model_turns": 1, "tool_calls": 0},
    )


@pytest.mark.asyncio
async def test_compat_chat_routes_text_through_engine_adapter(monkeypatch) -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return _response()

    monkeypatch.setattr(
        "core.ai_provider_compat.execute_engine_text",
        execute,
    )

    chat = (
        LlmChat(
            api_key="legacy-key",
            session_id="s",
            system_message="rules",
        )
        .with_model("openai", "requested-model")
        .with_max_tokens(321)
    )
    response = await chat.send_message(UserMessage(text="hello"))

    assert isinstance(response, ChatResponse)
    assert response == "answer"
    assert response.content == "answer"
    assert len(requests) == 1
    request = requests[0]
    assert request.instructions == "rules"
    assert request.prompt == "hello"
    assert request.max_output_tokens == 321
    assert request.capability == "assistant.compat"
    assert request.actor_id == "legacy-llm-chat"
    assert request.history == ()


@pytest.mark.asyncio
async def test_provider_and_model_hints_are_not_forwarded_to_engine(
    monkeypatch,
) -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return _response()

    monkeypatch.setattr(
        "core.ai_provider_compat.execute_engine_text",
        execute,
    )

    chat = LlmChat(system_message="rules").with_model(
        "anthropic",
        "claude-sonnet",
    )
    await chat.send_message("hello")

    request = requests[0]
    assert not hasattr(request, "provider")
    assert not hasattr(request, "model")
    assert request.capability == "assistant.compat"


@pytest.mark.asyncio
async def test_compat_chat_preserves_local_history(monkeypatch) -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return _response()

    monkeypatch.setattr(
        "core.ai_provider_compat.execute_engine_text",
        execute,
    )

    chat = LlmChat(system_message="rules")
    await chat.send_message("first")
    await chat.send_message("second")

    second = requests[1]
    assert second.history == (
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
    )
    assert second.idempotency_key != requests[0].idempotency_key


@pytest.mark.asyncio
async def test_legacy_aliases_delegate_to_engine_text(monkeypatch) -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return _response()

    monkeypatch.setattr(
        "core.ai_provider_compat.execute_engine_text",
        execute,
    )

    chat = LlmChat(
        "legacy-key",
        "session",
        "old rules",
    ).with_system_message("rules")
    assert await chat.chat(UserMessage(content="one")) == "answer"
    assert await chat.generate(UserMessage(message="two")) == "answer"
    assert [request.prompt for request in requests] == ["one", "two"]
    assert all(request.instructions == "rules" for request in requests)


@pytest.mark.asyncio
async def test_engine_failure_maps_to_legacy_provider_unavailable(
    monkeypatch,
) -> None:
    async def execute(_request):
        raise EngineTextError("engine-secret-must-not-leak")

    monkeypatch.setattr(
        "core.ai_provider_compat.execute_engine_text",
        execute,
    )

    chat = LlmChat(system_message="rules")
    with pytest.raises(
        ProviderUnavailableError,
        match="canonical engine text execution is unavailable",
    ) as caught:
        await chat.send_message("hello")

    assert "engine-secret-must-not-leak" not in str(caught.value)


@pytest.mark.asyncio
async def test_multimodal_legacy_surface_fails_explicitly() -> None:
    chat = LlmChat().with_params(modalities=["image", "text"])
    with pytest.raises(ProviderUnavailableError, match="multimodal"):
        await chat.send_message_multimodal_response(
            UserMessage(text="draw")
        )


def test_user_message_and_response_are_legacy_compatible() -> None:
    assert UserMessage(text="hello").content == "hello"
    assert UserMessage(content="hello").text == "hello"
    assert UserMessage(message="hello").text == "hello"
    response = ChatResponse("world")
    assert response.content == "world"


def test_compat_source_has_no_local_provider_activation() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "core"
        / "ai_provider_compat.py"
    ).read_text(encoding="utf-8")

    assert "ProviderRegistry.from_env(" not in source
    assert "from core.ai_provider import" not in source
    assert "execute_engine_text" in source
