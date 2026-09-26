from __future__ import annotations

import pytest

from core.engine_text import EngineTextError


class _FailingChat:
    def __init__(self, *_args, **_kwargs):
        pass

    def with_model(self, *_args, **_kwargs):
        return self

    async def send_message(self, _message):
        raise EngineTextError("engine unavailable")


class _BrokenChat:
    def __init__(self, *_args, **_kwargs):
        pass

    def with_model(self, *_args, **_kwargs):
        return self

    async def send_message(self, _message):
        raise RuntimeError("programming defect")


@pytest.mark.asyncio
async def test_code_intelligence_degrades_only_for_engine_text_error(
    monkeypatch,
) -> None:
    import routes.code_intelligence as route

    monkeypatch.setattr(route, "EngineChat", _FailingChat)

    result = await route.call_llm("system", "prompt")

    assert result == "llm_request_failed"


@pytest.mark.asyncio
async def test_code_intelligence_surfaces_unexpected_engine_boundary_defect(
    monkeypatch,
) -> None:
    import routes.code_intelligence as route

    monkeypatch.setattr(route, "EngineChat", _BrokenChat)

    with pytest.raises(RuntimeError, match="programming defect"):
        await route.call_llm("system", "prompt")
