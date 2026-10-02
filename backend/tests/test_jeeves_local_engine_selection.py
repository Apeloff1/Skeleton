from __future__ import annotations

from types import SimpleNamespace

import pytest

from routes import jeeves_compose


@pytest.mark.asyncio
async def test_active_local_engine_uses_local_model_instead_of_extractive_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        jeeves_compose.free_tier,
        "decide",
        lambda _needs_reasoning: "local",
    )

    async def local_active():
        return True

    monkeypatch.setattr(
        jeeves_compose,
        "_local_engine_provider_active",
        local_active,
    )

    calls: list[tuple[str, object]] = []

    class FakeEngineChat:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def with_max_tokens(self, value):
            calls.append(("max_tokens", value))
            return self

        def add_history_message(self, role, content):
            calls.append(("history", (role, content)))
            return self

        def add_evidence(self, source_id, content, *, kind="retrieval_evidence"):
            calls.append(
                ("evidence", (source_id, content, kind))
            )
            return self

        async def send_message(self, message):
            calls.append(("send", message.text))
            return SimpleNamespace(
                text="Actual local model answer",
                operation_id="operation-local-jeeves",
                execution_id="execution-local-jeeves",
                context_id="context-local-jeeves",
                context_digest="e" * 64,
                context_source_snapshot=(
                    ("segment-local-jeeves", "f" * 64),
                ),
                context_compiler_version="compiler-local-jeeves",
                verification="verification:local",
                evidence_refs=("evidence:local",),
                provider_receipts=("provider:local:jeeves",),
                tool_receipts=(),
                memory_refs=(),
                artifact_refs=(),
            )

    monkeypatch.setattr(
        jeeves_compose,
        "EngineChat",
        FakeEngineChat,
    )

    result = await jeeves_compose._generate_text(
        "short",
        [{"payload": {"content": "extractive material"}}],
        False,
    )

    assert result["text"] == "Actual local model answer"
    assert result["tier"] == "local-model"
    assert result["model"] == "skeleton-engine"
    assert result["engine_execution_id"] == "execution-local-jeeves"
    assert result["engine_operation_id"] == "operation-local-jeeves"
    assert result["engine_provider_receipts"] == [
        "provider:local:jeeves"
    ]
    assert ("send", "short") in calls
    evidence_calls = [
        value for kind, value in calls if kind == "evidence"
    ]
    assert len(evidence_calls) == 1
    assert evidence_calls[0][2] == "retrieval_evidence"
    assert "extractive material" in evidence_calls[0][1]


@pytest.mark.asyncio
async def test_extractive_mode_stays_explicit_without_active_local_engine(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        jeeves_compose.free_tier,
        "decide",
        lambda _needs_reasoning: "local",
    )

    async def local_inactive():
        return False

    monkeypatch.setattr(
        jeeves_compose,
        "_local_engine_provider_active",
        local_inactive,
    )

    class UnexpectedEngineChat:
        def __init__(self, **_kwargs):
            raise AssertionError(
                "extractive mode must remain distinct from engine inference"
            )

    monkeypatch.setattr(
        jeeves_compose,
        "EngineChat",
        UnexpectedEngineChat,
    )

    result = await jeeves_compose._generate_text(
        "short",
        [{"payload": {"content": "bounded extractive result"}}],
        False,
    )

    assert result["text"] == "bounded extractive result"
    assert result["model"] == "local-extractive"
    assert result["engine_execution_id"] is None
    assert result["engine_verification"] is None
