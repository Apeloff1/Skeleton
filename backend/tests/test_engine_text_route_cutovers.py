from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from core.engine_text import EngineTextError, EngineTextResponse
from routes import ai_debugger, ai_pipeline, ai_toolkit_enhanced


ROOT = Path(__file__).resolve().parents[1]


def _response(text: str = "engine answer") -> EngineTextResponse:
    return EngineTextResponse(
        text=text,
        execution_id="exec-route-cutover",
        verification="verification:route-cutover",
        evidence_refs=(),
        usage={"model_turns": 1, "tool_calls": 0},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "helper_name", "actor_id", "purpose"),
    (
        (
            ai_debugger,
            "call_debugger_ai",
            "ai-debugger",
            "code-debugging",
        ),
        (
            ai_pipeline,
            "call_gpt4o",
            "ai-pipeline",
            "ai-pipeline-text-generation",
        ),
        (
            ai_toolkit_enhanced,
            "call_ai",
            "ai-toolkit",
            "software-engineering-assistance",
        ),
    ),
)
async def test_text_route_helper_delegates_to_engine(
    monkeypatch,
    module,
    helper_name,
    actor_id,
    purpose,
) -> None:
    captured = []

    async def execute(request):
        captured.append(request)
        return _response()

    monkeypatch.setattr(module, "execute_engine_text", execute)
    helper = getattr(module, helper_name)

    if helper_name == "call_gpt4o":
        result = await helper(
            "Prompt",
            "System",
            max_tokens=777,
        )
    else:
        result = await helper("Prompt", "System")

    assert result == "engine answer"
    assert len(captured) == 1
    request = captured[0]
    assert request.actor_id == actor_id
    assert request.capability == "assistant.compat"
    assert request.verification_profile == "assistant_proposal"
    assert request.purpose == purpose
    assert request.instructions == "System"
    assert request.prompt == "Prompt"
    if helper_name == "call_gpt4o":
        assert request.max_output_tokens == 777
    else:
        assert request.max_output_tokens == 16_384
    assert request.idempotency_key.startswith(actor_id + ":")


@pytest.mark.asyncio
async def test_debugger_engine_failure_maps_to_stable_503(monkeypatch) -> None:
    async def execute(_request):
        raise EngineTextError("private-provider-detail")

    monkeypatch.setattr(
        ai_debugger,
        "execute_engine_text",
        execute,
    )
    with pytest.raises(HTTPException) as caught:
        await ai_debugger.call_debugger_ai("Prompt", "System")

    assert caught.value.status_code == 503
    assert caught.value.detail == "AI debugger engine failed"
    assert "private-provider-detail" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_pipeline_engine_failure_maps_to_stable_503(monkeypatch) -> None:
    async def execute(_request):
        raise EngineTextError("private-provider-detail")

    monkeypatch.setattr(
        ai_pipeline,
        "execute_engine_text",
        execute,
    )
    with pytest.raises(HTTPException) as caught:
        await ai_pipeline.call_gpt4o("Prompt", "System")

    assert caught.value.status_code == 503
    assert caught.value.detail == "AI text generation failed"
    assert "private-provider-detail" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_toolkit_engine_failure_keeps_legacy_sentinel(monkeypatch) -> None:
    async def execute(_request):
        raise EngineTextError("private-provider-detail")

    monkeypatch.setattr(
        ai_toolkit_enhanced,
        "execute_engine_text",
        execute,
    )
    result = await ai_toolkit_enhanced.call_ai("Prompt", "System")

    assert result == "llm_request_failed"


@pytest.mark.parametrize(
    "relative",
    (
        "routes/ai_debugger.py",
        "routes/ai_pipeline.py",
        "routes/ai_toolkit_enhanced.py",
    ),
)
def test_text_route_source_has_no_local_provider_activation(relative: str) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")

    assert "ProviderRegistry.from_env(" not in source
    assert "ProviderRequest(" not in source
    assert "from core.ai_provider import" not in source
    assert "EngineTextRequest" in source
    assert "execute_engine_text" in source
