from __future__ import annotations

from enum import Enum
from pathlib import Path

import pytest

from core.engine_client import EngineClientConfig
from core.engine_text import EngineTextError, EngineTextResponse
from services import ai_hub_svc


ROOT = Path(__file__).resolve().parents[1]


class _Provider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROK = "grok"


def _engine_response(text: str) -> EngineTextResponse:
    return EngineTextResponse(
        text=text,
        execution_id="exec-ai-hub",
        verification="verification:ai-hub",
        evidence_refs=(),
        usage={"model_turns": 1, "tool_calls": 0},
    )


@pytest.fixture(autouse=True)
def _provider_enum(monkeypatch):
    monkeypatch.setattr(
        ai_hub_svc,
        "_llm_provider_enum",
        lambda: _Provider,
    )


@pytest.fixture
def configured_engine(monkeypatch):
    fake = type(
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
        ai_hub_svc.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )
    return fake


def test_ai_hub_reports_engine_boundary_not_legacy_provider(
    configured_engine,
) -> None:
    hub = ai_hub_svc.AIHubService()
    status = hub.provider_status()

    assert hub.available is True
    assert hub.api_key == "configured"
    assert status["active"] == "skeleton-engine"
    assert status["available"] is True
    assert status["providers"][0]["ownership"] == "engine-process"
    for provider in _Provider:
        assert hub.providers[provider]["declared"] is False
        assert hub.providers[provider]["available"] is False
        assert hub.providers[provider]["model"] == "engine-routed"


@pytest.mark.asyncio
async def test_ai_hub_suggestion_uses_engine_proposal_profile(
    configured_engine,
) -> None:
    captured = []

    async def execute(request):
        captured.append(request)
        return _engine_response(
            '[{"id":"x","name":"X","description":"D","category":"c",'
            '"impact":"high","implementation_difficulty":"low"}]'
        )

    hub = ai_hub_svc.AIHubService(engine_executor=execute)
    result = await hub.suggest_features({"languages": ["python"]})

    assert result[0]["id"] == "x"
    assert len(captured) == 1
    request = captured[0]
    assert "compiler and IDE feature analyst" in request.instructions
    assert "Languages used" in request.prompt
    assert request.max_output_tokens == 1800
    assert request.verification_profile == "assistant_proposal"
    assert request.capability == "assistant.compat"


@pytest.mark.asyncio
async def test_ai_hub_falls_back_on_engine_failure(
    configured_engine,
) -> None:
    async def execute(_request):
        raise EngineTextError("private-upstream-detail")

    hub = ai_hub_svc.AIHubService(engine_executor=execute)
    result = await hub.suggest_features({})

    assert result
    assert result[0]["id"] == "smart_completion"
    assert "private-upstream-detail" not in str(result)


@pytest.mark.asyncio
async def test_ai_hub_sota_requires_evidence_profile(
    configured_engine,
) -> None:
    captured = []

    async def execute(request):
        captured.append(request)
        raise EngineTextError("evidence unavailable")

    hub = ai_hub_svc.AIHubService(engine_executor=execute)
    result = await hub.query_sota("Python runtimes")

    assert result == {
        "status": "offline",
        "domain": "Python runtimes",
        "message": "engine_unavailable",
    }
    assert captured[0].verification_profile == "evidence_required"
    assert captured[0].max_output_tokens == 2200


def test_legacy_assistant_source_delegates_to_engine_without_local_provider() -> None:
    source = (
        ROOT / "services" / "ai_assistant_svc.py"
    ).read_text(encoding="utf-8")

    assert "from openai import" not in source
    assert "import openai" not in source
    assert "skeleton.frontier.model_runtime" not in source
    assert "ProviderRegistry" not in source
    assert "ProviderRequest" not in source
    assert "EngineTextRequest" in source
    assert "execute_engine_text" in source


def test_hub_source_has_no_local_provider_or_legacy_chat_shim() -> None:
    source = (
        ROOT / "services" / "ai_hub_svc.py"
    ).read_text(encoding="utf-8")

    assert "EMERGENT_LLM_KEY" not in source
    assert "emergentintegrations" not in source
    assert "ProviderRegistry" not in source
    assert "ProviderRequest" not in source
    assert "EngineTextRequest" in source
    assert "execute_engine_text" in source
