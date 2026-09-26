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
async def test_sota_predictive_route_degrades_on_engine_text_error(
    monkeypatch,
) -> None:
    import routes.sota_2026 as route

    monkeypatch.setattr(route, "EngineChat", _FailingChat)

    result = await route.predictive_assistance(
        route.PredictiveRequest(code="x = 1")
    )

    assert result == {
        "predictions": [],
        "error": "prediction_failed",
    }


@pytest.mark.asyncio
async def test_sota_predictive_route_surfaces_unexpected_engine_defect(
    monkeypatch,
) -> None:
    import routes.sota_2026 as route

    monkeypatch.setattr(route, "EngineChat", _BrokenChat)

    with pytest.raises(RuntimeError, match="programming defect"):
        await route.predictive_assistance(
            route.PredictiveRequest(code="x = 1")
        )
