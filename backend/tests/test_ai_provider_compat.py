from __future__ import annotations

import pytest

from core.ai_provider import ProviderResponse, ProviderUnavailableError
from core.ai_provider_compat import ChatResponse, LlmChat, UserMessage


class _FakeAdapter:
    provider_id = "openai"

    def __init__(self) -> None:
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(
            text="answer",
            provider="openai",
            model=request.model or "configured-model",
        )


class _FakeRegistry:
    def __init__(self, adapter: _FakeAdapter) -> None:
        self.adapter = adapter

    def require_active(self):
        return self.adapter


@pytest.mark.asyncio
async def test_compat_chat_routes_text_through_canonical_provider(monkeypatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(
        "core.ai_provider_compat.ProviderRegistry.from_env",
        lambda: _FakeRegistry(adapter),
    )

    chat = (
        LlmChat(api_key="legacy-key", session_id="s", system_message="rules")
        .with_model("openai", "requested-model")
        .with_max_tokens(321)
    )
    response = await chat.send_message(UserMessage(text="hello"))

    assert isinstance(response, ChatResponse)
    assert response == "answer"
    assert response.content == "answer"
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.instructions == "rules"
    assert request.prompt == "hello"
    assert request.model == "requested-model"
    assert request.max_output_tokens == 321


@pytest.mark.asyncio
async def test_cross_provider_model_hint_is_not_forwarded(monkeypatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(
        "core.ai_provider_compat.ProviderRegistry.from_env",
        lambda: _FakeRegistry(adapter),
    )

    chat = LlmChat(system_message="rules").with_model("anthropic", "claude-sonnet")
    await chat.send_message("hello")

    assert adapter.requests[0].model is None


@pytest.mark.asyncio
async def test_compat_chat_preserves_local_history(monkeypatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(
        "core.ai_provider_compat.ProviderRegistry.from_env",
        lambda: _FakeRegistry(adapter),
    )

    chat = LlmChat(system_message="rules")
    await chat.send_message("first")
    await chat.send_message("second")

    second = adapter.requests[1]
    assert [(m.role, m.content) for m in second.history] == [
        ("user", "first"),
        ("assistant", "answer"),
    ]


@pytest.mark.asyncio
async def test_multimodal_legacy_surface_fails_explicitly() -> None:
    chat = LlmChat().with_params(modalities=["image", "text"])
    with pytest.raises(ProviderUnavailableError, match="multimodal"):
        await chat.send_message_multimodal_response(UserMessage(text="draw"))


def test_user_message_and_response_are_legacy_compatible() -> None:
    message = UserMessage(text="hello")
    assert message.content == "hello"
    response = ChatResponse("world")
    assert response.content == "world"
