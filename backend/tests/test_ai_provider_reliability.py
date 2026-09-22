"""Deterministic provider-boundary chaos regressions for reliability issue #123."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core.ai_provider import (
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderRegistry,
    ProviderRequest,
    ProviderUnavailableError,
)
from core.provider_architecture import ProviderArchitectureReceipt
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


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.openai.com/v1",
        "https://user:password@provider.invalid/v1",
        "https://localhost/v1",
        "https://service.localhost/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://10.0.0.1/v1",
        "https://2130706433/v1",
        "https://metadata.google.internal/computeMetadata/v1",
        "https://provider.invalid/v1?target=internal",
        "https://provider.invalid/v1#fragment",
    ],
)
def test_sdk_client_rejects_unsafe_custom_base_urls(base_url, monkeypatch) -> None:
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        base_url=base_url,
    )

    def _must_not_load_sdk():
        pytest.fail("provider SDK must not load before base URL validation")

    monkeypatch.setattr(adapter, "_load_client_class", _must_not_load_sdk)

    with pytest.raises(ProviderUnavailableError, match="base URL"):
        adapter._get_client()


def test_invalid_custom_base_url_marks_provider_unavailable(monkeypatch) -> None:
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="test-model",
        base_url="https://127.0.0.1/v1",
    )

    def _must_not_load_sdk():
        pytest.fail("provider SDK must not load for an invalid base URL")

    monkeypatch.setattr(adapter, "_load_client_class", _must_not_load_sdk)

    assert adapter.available is False


def test_route_boundary_hides_provider_failure_details(monkeypatch, caplog) -> None:
    registry = ProviderRegistry(
        [_FailingAdapter()],
        active="chaos",
        architecture_loader=lambda provider_id: ProviderArchitectureReceipt(
            provider_id=provider_id,
            architecture_tag="arch-map/test",
            construction_version="test",
            contract_digest="0" * 64,
            manual_path="docs/AI_APP_CONSTRUCTION_MANUAL.md",
            required_documents=("machine/architecture.json",),
        ),
    )
    monkeypatch.setattr(ai_routes, "AI_REGISTRY", registry)

    result = asyncio.run(ai_routes.call_llm("rules", "hello"))

    assert result == {
        "success": False,
        "error": "AI provider is unavailable",
        "error_code": "provider_unavailable",
    }
    assert "upstream-token=do-not-leak" not in caplog.text
    assert "ProviderInvocationError" in caplog.text
