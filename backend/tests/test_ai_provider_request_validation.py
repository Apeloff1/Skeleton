from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.ai_provider import (
    AIMessage,
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderPolicyError,
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


@pytest.mark.asyncio
async def test_restricted_data_is_denied_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="sensitive input",
                data_class="restricted",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_confidential_data_requires_tenant_binding(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="tenant data",
                data_class="confidential",
                purpose="code-assistance",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_confidential_tenant_transfer_emits_governance_receipt(
    adapter: OpenAIProviderAdapter,
) -> None:
    result = await adapter.generate(
        ProviderRequest(
            instructions="rules",
            prompt="tenant data",
            data_class="confidential",
            purpose="code-assistance",
            tenant_id="tenant-123",
        )
    )

    assert result.text == "ok"
    assert result.data_class == "confidential"
    assert result.governance_decision_id
    assert result.governance_decision_id.startswith("gov-")
    assert adapter._client.responses.calls == 1


@pytest.mark.asyncio
async def test_unknown_provider_transfer_purpose_fails_closed(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                purpose="invented-side-channel",
            )
        )

    assert adapter._client.responses.calls == 0
