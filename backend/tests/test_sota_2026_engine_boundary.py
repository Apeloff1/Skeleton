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


def test_sota_policy_chat_binds_named_instruction_policy(
    monkeypatch,
) -> None:
    import routes.sota_2026 as route

    seen = {}

    class RecordingChat:
        def __init__(self, *_args, **kwargs):
            seen.update(kwargs)

        def with_model(self, *_args, **_kwargs):
            return self

    monkeypatch.setattr(route, "EngineChat", RecordingChat)

    chat = route._policy_chat(
        "backend.sota.predictive",
        "Canonical predictive rules.",
    )

    assert isinstance(chat, RecordingChat)
    policy = seen["instruction_policy"]
    assert policy.policy_id == "backend.sota.predictive"
    assert policy.version == "1"
    assert policy.instructions == "Canonical predictive rules."
    assert seen["actor_id"] == "sota-2026"
    assert seen["capability"] == "assistant.compat"


def test_sota_source_has_no_anonymous_enginechat_system_message() -> None:
    import inspect
    import routes.sota_2026 as route

    source = inspect.getsource(route)

    assert "EngineChat(\n            system_message=" not in source
    assert "EngineChat(\n                system_message=" not in source
