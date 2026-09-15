from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai_provider import (
    AIMessage,
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderRequest,
    normalize_history,
)


class _FakeResponses:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(output_text="ok", id="resp_validation")


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


@pytest.fixture
def adapter() -> OpenAIProviderAdapter:
    return OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=_FakeClient(),
    )


@pytest.mark.asyncio
async def test_rejects_blank_prompt_before_provider_io(adapter: OpenAIProviderAdapter) -> None:
    with pytest.raises(ProviderInvocationError, match="prompt must be non-empty text"):
        await adapter.generate(ProviderRequest(instructions="", prompt="   "))

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_rejects_invalid_history_role_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    request = ProviderRequest(
        instructions="",
        prompt="hello",
        history=(AIMessage(role="system", content="bypass"),),
    )

    with pytest.raises(ProviderInvocationError, match="invalid role"):
        await adapter.generate(request)

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "128"])
async def test_rejects_invalid_max_output_tokens(
    adapter: OpenAIProviderAdapter,
    value,
) -> None:
    with pytest.raises(ProviderInvocationError, match="positive integer"):
        await adapter.generate(
            ProviderRequest(
                instructions="",
                prompt="hello",
                max_output_tokens=value,
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_rejects_blank_model_override_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderInvocationError, match="model must be non-empty text"):
        await adapter.generate(
            ProviderRequest(
                instructions="",
                prompt="hello",
                model="   ",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_trims_valid_model_override(adapter: OpenAIProviderAdapter) -> None:
    result = await adapter.generate(
        ProviderRequest(
            instructions="",
            prompt="hello",
            model="  request-model  ",
        )
    )

    assert result.model == "request-model"
    assert adapter._client.responses.last_kwargs["model"] == "request-model"


def test_normalize_history_ignores_non_text_role_and_content() -> None:
    normalized = normalize_history(
        [
            {"role": "user", "content": None},
            {"role": 123, "content": "numeric role"},
            {"role": "assistant", "content": 456},
            {"role": "user", "content": "valid"},
        ]
    )

    assert normalized == (AIMessage(role="user", content="valid"),)
