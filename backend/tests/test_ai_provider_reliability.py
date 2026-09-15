"""Deterministic provider-boundary chaos regressions for reliability issue #123."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.ai_provider import (
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderRegistry,
    ProviderRequest,
)
from routes import ai as ai_routes


class _TimeoutResponses:
    def __init__(self, detail: str) -> None:
        self.detail = detail
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        raise TimeoutError(self.detail)


class _Client:
    def __init__(self, responses) -> None:
        self.responses = responses


class _FailingAdapter:
    provider_id = "chaos"
    model = "chaos-model"
    available = True

    def status(self):
        return {"id": self.provider_id, "model": self.model, "available": True}

    async def generate(self, _request):
        raise ProviderInvocationError("upstream-token=do-not-leak")


def test_timeout_burst_is_bounded_and_sanitized() -> None:
    secret = "provider-timeout secret=do-not-leak"
    responses = _TimeoutResponses(secret)
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        client=_Client(responses),
    )
    request = ProviderRequest(instructions="rules", prompt="hello")

    async def scenario():
        return await asyncio.gather(
            *(adapter.generate(request) for _ in range(32)),
            return_exceptions=True,
        )

    outcomes = asyncio.run(scenario())

    assert responses.calls == 32
    assert len(outcomes) == 32
    assert all(isinstance(outcome, ProviderInvocationError) for outcome in outcomes)
    assert all(str(outcome) == "model provider request failed" for outcome in outcomes)
    assert all(secret not in str(outcome) for outcome in outcomes)


def test_sdk_client_receives_explicit_timeout_and_retry_bounds(monkeypatch) -> None:
    captured = {}

    class _CapturedClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.responses = SimpleNamespace()

    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        base_url="https://provider.invalid/v1",
        timeout_seconds=7.5,
        max_retries=3,
    )
    monkeypatch.setattr(adapter, "_load_client_class", lambda: _CapturedClient)

    client = adapter._get_client()

    assert isinstance(client, _CapturedClient)
    assert captured == {
        "api_key": "test-key",
        "timeout": 7.5,
        "max_retries": 3,
        "base_url": "https://provider.invalid/v1",
    }


def test_route_boundary_hides_provider_failure_details(monkeypatch, caplog) -> None:
    registry = ProviderRegistry([_FailingAdapter()], active="chaos")
    monkeypatch.setattr(ai_routes, "AI_REGISTRY", registry)

    result = asyncio.run(ai_routes.call_llm("rules", "hello"))

    assert result == {
        "success": False,
        "error": "AI provider is unavailable",
        "error_code": "provider_unavailable",
    }
    assert "upstream-token=do-not-leak" not in caplog.text
    assert "ProviderInvocationError" in caplog.text
