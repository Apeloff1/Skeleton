from __future__ import annotations

from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.ai_provider import ProviderResponse, ProviderUnavailableError
from services import ai_hub_svc


ROOT = Path(__file__).resolve().parents[1]


class _Provider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROK = "grok"


class _FakeAdapter:
    provider_id = "openai"
    model = "test-model"
    available = True

    def __init__(self, text: str = "answer") -> None:
        self.text = text
        self.requests = []

    def status(self):
        return {"id": "openai", "model": self.model, "available": True}

    async def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(
            text=self.text,
            provider="openai",
            model=request.model or self.model,
            request_id="req-test",
        )


class _FakeRegistry:
    active_id = "openai"

    def __init__(self, adapter: _FakeAdapter, *, available: bool = True) -> None:
        self._adapter = adapter
        self._available = available

    @property
    def active(self):
        return self._adapter

    @property
    def available(self):
        return self._available

    def require_active(self):
        if not self._available:
            raise ProviderUnavailableError("provider unavailable")
        return self._adapter

    def statuses(self):
        return [
            {
                "id": "openai",
                "model": self._adapter.model,
                "available": self._available,
                "active": True,
                "architecture_acknowledged": True,
                "architecture_tag": "arch-map/test",
                "construction_version": "test",
            }
        ]


@pytest.fixture(autouse=True)
def _provider_enum(monkeypatch):
    monkeypatch.setattr(ai_hub_svc, "_llm_provider_enum", lambda: _Provider)


def test_ai_hub_reports_only_declared_provider_as_available() -> None:
    hub = ai_hub_svc.AIHubService(registry=_FakeRegistry(_FakeAdapter()))

    assert hub.providers[_Provider.OPENAI]["declared"] is True
    assert hub.providers[_Provider.OPENAI]["available"] is True
    for provider in (_Provider.ANTHROPIC, _Provider.GOOGLE, _Provider.GROK):
        assert hub.providers[provider]["declared"] is False
        assert hub.providers[provider]["available"] is False


@pytest.mark.asyncio
async def test_ai_hub_generation_uses_canonical_provider_request() -> None:
    adapter = _FakeAdapter(
        '[{"id":"x","name":"X","description":"D","category":"c","impact":"high","implementation_difficulty":"low"}]'
    )
    hub = ai_hub_svc.AIHubService(registry=_FakeRegistry(adapter))

    result = await hub.suggest_features({"languages": ["python"]})

    assert result[0]["id"] == "x"
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert "compiler and IDE feature analyst" in request.instructions
    assert "Languages used" in request.prompt
    assert request.max_output_tokens == 1800


@pytest.mark.asyncio
async def test_ai_hub_falls_back_without_provider() -> None:
    hub = ai_hub_svc.AIHubService(
        registry=_FakeRegistry(_FakeAdapter(), available=False)
    )

    result = await hub.suggest_features({})

    assert result
    assert result[0]["id"] == "smart_completion"


def test_legacy_assistant_source_delegates_to_engine_without_local_provider() -> None:
    source = (ROOT / "services/ai_assistant_svc.py").read_text(encoding="utf-8")

    assert "from openai import" not in source
    assert "import openai" not in source
    assert "skeleton.frontier.model_runtime" not in source
    assert "ProviderRegistry" not in source
    assert "ProviderRequest" not in source
    assert "EngineTextRequest" in source
    assert "execute_engine_text" in source


def test_hub_source_has_no_universal_provider_key_or_legacy_chat_shim() -> None:
    source = (ROOT / "services/ai_hub_svc.py").read_text(encoding="utf-8")

    assert "EMERGENT_LLM_KEY" not in source
    assert "emergentintegrations" not in source
    assert "ProviderRegistry" in source
    assert "ProviderRequest" in source
