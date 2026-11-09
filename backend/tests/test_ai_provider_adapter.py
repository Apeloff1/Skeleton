from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from core.ai_provider import (
    AIMessage,
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderRegistry,
    ProviderRequest,
    ProviderUnavailableError,
    normalize_history,
)


class _FakeResponses:
    def __init__(self, *, text: str = "ok", response_id: str = "resp_test") -> None:
        self.text = text
        self.response_id = response_id
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(output_text=self.text, id=self.response_id)


class _FakeClient:
    def __init__(self, responses: _FakeResponses) -> None:
        self.responses = responses


class _TailOnlyHistory(Sequence):
    """Sequence that fails if normalization scans the irrelevant old prefix."""

    def __len__(self) -> int:
        return 1_000

    def __getitem__(self, index: int) -> Any:
        if index == 999:
            return {"role": "user", "content": "tail"}
        if 0 <= index < 999:
            raise AssertionError("history normalization scanned past a full newest-first budget")
        raise IndexError(index)


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_response_and_preserves_history() -> None:
    responses = _FakeResponses(text="model answer")
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=_FakeClient(responses),
    )

    result = await adapter.generate(
        ProviderRequest(
            instructions="system rules",
            prompt="current question",
            history=(
                AIMessage(role="user", content="older question"),
                AIMessage(role="assistant", content="older answer"),
            ),
            max_output_tokens=512,
            model="request-model",
        )
    )

    assert result.text == "model answer"
    assert result.provider == "openai"
    assert result.model == "request-model"
    assert result.request_id == "resp_test"
    assert result.latency_ms is not None
    assert responses.last_kwargs == {
        "model": "request-model",
        "instructions": "system rules",
        "input": [
            {"role": "user", "content": "older question"},
            {"role": "assistant", "content": "older answer"},
            {"role": "user", "content": "current question"},
        ],
        "max_output_tokens": 512,
    }


@pytest.mark.asyncio
async def test_openai_adapter_rejects_empty_model_output() -> None:
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        client=_FakeClient(_FakeResponses(text="   ")),
    )

    with pytest.raises(ProviderInvocationError, match="no normalized output"):
        await adapter.generate(ProviderRequest(instructions="rules", prompt="hello"))


def test_openai_adapter_without_key_is_not_available(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIProviderAdapter(api_key="")

    assert adapter.available is False
    registry = ProviderRegistry([adapter], active="openai")
    assert registry.available is False
    with pytest.raises(ProviderUnavailableError):
        registry.require_active()


def test_registry_rejects_unknown_selected_provider() -> None:
    adapter = OpenAIProviderAdapter(api_key="", model="test-model")
    registry = ProviderRegistry([adapter], active="unknown")

    assert registry.active is None
    assert registry.available is False
    with pytest.raises(ProviderUnavailableError, match="unsupported AI provider"):
        registry.require_active()


def test_normalize_history_filters_roles_and_keeps_newest_with_budget() -> None:
    history = [
        {"role": "system", "content": "ignore me"},
        {"role": "user", "content": "12345"},
        {"role": "assistant", "content": "67890"},
        {"role": "tool", "content": "ignore me too"},
        {"role": "user", "content": "abcde"},
    ]

    normalized = normalize_history(history, char_budget=8)

    assert normalized == (
        AIMessage(role="assistant", content="890"),
        AIMessage(role="user", content="abcde"),
    )


def test_normalize_history_stops_scanning_sequence_once_budget_is_full() -> None:
    normalized = normalize_history(_TailOnlyHistory(), char_budget=4)

    assert normalized == (AIMessage(role="user", content="tail"),)


def test_normalize_history_bounds_generic_iterable_tail() -> None:
    history = iter(
        [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "older"},
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "abcdefgh"},
        ]
    )

    normalized = normalize_history(history, char_budget=5)

    assert normalized == (AIMessage(role="user", content="defgh"),)
