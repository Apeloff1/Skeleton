"""Hosted Jeeves provider contract without requiring an unrelated backend service.

Uses the real engine OpenAI adapter and injected fake Responses transport.
No provider request or API key is sent over a real network. Live model
qualification is a separate first-install acceptance gate.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from skeleton.provider_runtime import (
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderRequest,
    ProviderUnavailableError,
)


class CapturedSDK:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.responses = SimpleNamespace()


class TimeoutResponses:
    def __init__(self, secret: str):
        self.secret = secret
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        raise TimeoutError(self.secret)


class ControlledClient:
    def __init__(self, responses):
        self.responses = responses


def test_real_hosted_runtime_loads_sdk_without_logging_credentials(monkeypatch):
    captured = {}
    key = "sk-" + "Z" * 50
    adapter = OpenAIProviderAdapter(
        api_key=key, model="gpt-5.5", timeout_seconds=13.0, max_retries=2,
    )

    def make_sdk(**kwargs):
        captured.update(kwargs)
        return CapturedSDK(**kwargs)

    monkeypatch.setattr(adapter, "_load_client_class", lambda: make_sdk)
    client = adapter._get_client()
    assert isinstance(client, CapturedSDK)
    assert client.kwargs["api_key"] == key
    assert client.kwargs["timeout"] == 13.0
    assert client.kwargs["max_retries"] == 2
    assert adapter.model == "gpt-5.5"
    assert key not in repr(adapter)
    assert adapter.provider_id == "openai"


def test_unconfigured_hosted_model_is_unavailable_and_cannot_load_sdk():
    adapter = OpenAIProviderAdapter(api_key="", model="gpt-5.5")
    assert adapter.available is False
    with pytest.raises(ProviderUnavailableError):
        adapter._get_client()


def test_actual_hosted_adapter_bounds_timeout_and_redacts_upstream_secret():
    private = "upstream-error bearer-token=never-expose-me"
    responses = TimeoutResponses(private)
    adapter = OpenAIProviderAdapter(
        api_key="sk-" + "A" * 50,
        model="gpt-5.5",
        client=ControlledClient(responses),
        timeout_seconds=3.0,
        max_retries=2,
    )

    async def scenario():
        return await asyncio.gather(
            *(adapter.generate(ProviderRequest(instructions="safe", prompt="short response")) for _ in range(8)),
            return_exceptions=True,
        )

    outcomes = asyncio.run(scenario())
    assert responses.calls == 8
    assert all(isinstance(outcome, ProviderInvocationError) for outcome in outcomes)
    assert all(private not in str(outcome) for outcome in outcomes)
    assert all(str(outcome) == "model provider deadline exceeded" for outcome in outcomes)
