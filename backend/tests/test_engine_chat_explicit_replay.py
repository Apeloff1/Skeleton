"""An explicit chat idempotency key is a single immutable turn identity."""
from __future__ import annotations

import pytest

from core.engine_chat import EngineChat
from core.engine_text import EngineTextError, EngineTextResponse


def terminal(n: int) -> EngineTextResponse:
    return EngineTextResponse(
        text=f"answer-{n}", execution_id=f"execution-{n}",
        verification="verified", evidence_refs=(), usage={"input_tokens": 2, "output_tokens": 2},
    )


@pytest.mark.asyncio
async def test_identical_explicit_turn_replays_without_duplicate_generation() -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return terminal(len(requests))

    chat = EngineChat(
        session_id="replay", turn_idempotency_key="original-turn", engine_executor=execute,
    )
    first = await chat.send_message("Create an original scene.")
    second = await chat.send_message("Create an original scene.")
    assert str(first) == "answer-1"
    assert second == first
    assert len(requests) == 1
    assert chat._history == [
        {"role": "user", "content": "Create an original scene."},
        {"role": "assistant", "content": "answer-1"},
    ]


@pytest.mark.asyncio
async def test_key_reuse_cannot_change_prompt_or_semantic_options() -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return terminal(len(requests))

    chat = EngineChat(
        session_id="semantic", turn_idempotency_key="same-key", engine_executor=execute,
    )
    await chat.send_message("First original scene")
    with pytest.raises(EngineTextError, match="changed chat request"):
        await chat.send_message("Different scene")
    chat.with_max_tokens(30)
    with pytest.raises(EngineTextError, match="changed chat request"):
        await chat.send_message("First original scene")
    assert len(requests) == 1
    assert len(chat._history) == 2


@pytest.mark.asyncio
async def test_explicit_replay_rejects_modified_prior_history() -> None:
    requests = []

    async def execute(request):
        requests.append(request)
        return terminal(len(requests))

    chat = EngineChat(
        session_id="changed-context", turn_idempotency_key="key-1",
        engine_executor=execute,
    )
    await chat.send_message("Question")
    chat.add_history_message("user", "Additional event")
    with pytest.raises(EngineTextError, match="changed chat request"):
        await chat.send_message("Question")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_failed_terminal_does_not_cache_explicit_turn() -> None:
    count = 0

    async def execute(request):
        nonlocal count
        count += 1
        if count == 1:
            raise EngineTextError("model unavailable")
        return terminal(count)

    chat = EngineChat(
        session_id="failed", turn_idempotency_key="retry-1",
        engine_executor=execute,
    )
    with pytest.raises(EngineTextError, match="unavailable"):
        await chat.send_message("Try again")
    assert chat._history == []
    result = await chat.send_message("Try again")
    assert str(result) == "answer-2"
    assert count == 2
    assert len(chat._history) == 2
