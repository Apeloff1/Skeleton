"""Chat projection must remain ordered, typed and bounded under concurrency."""
from __future__ import annotations

import asyncio

import pytest

from core.engine_chat import EngineChat
from core.engine_text import EngineTextError, EngineTextResponse


def _answer(number: int, *, content: str | None = None) -> EngineTextResponse:
    return EngineTextResponse(
        text=content if content is not None else f"answer-{number}",
        execution_id=f"execution-{number}",
        verification="verified",
        evidence_refs=(),
        usage={"input_tokens": 2, "output_tokens": 2},
    )


@pytest.mark.asyncio
async def test_concurrent_chat_sends_serialize_history_and_context() -> None:
    first_started = asyncio.Event()
    first_release = asyncio.Event()
    requests = []

    async def executor(request):
        requests.append(request)
        if len(requests) == 1:
            first_started.set()
            await first_release.wait()
        return _answer(len(requests))

    chat = EngineChat(session_id="one", engine_executor=executor)
    first = asyncio.create_task(chat.send_message("first question"))
    await asyncio.wait_for(first_started.wait(), timeout=5)
    second = asyncio.create_task(chat.send_message("second question"))
    await asyncio.sleep(0)
    assert len(requests) == 1
    first_release.set()
    responses = await asyncio.gather(first, second)
    assert [str(x) for x in responses] == ["answer-1", "answer-2"]
    assert requests[0].history == ()
    assert requests[1].history == (
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "answer-1"},
    )
    assert chat._history[-2:] == [
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "answer-2"},
    ]
    assert requests[0].idempotency_key != requests[1].idempotency_key


@pytest.mark.asyncio
async def test_noncanonical_executor_terminal_never_advances_history() -> None:
    async def invalid(_request):
        return {"text": "ungoverned"}

    chat = EngineChat(session_id="fail", engine_executor=invalid)
    with pytest.raises(EngineTextError, match="canonical typed terminal"):
        await chat.send_message("question")
    assert chat._history == []


@pytest.mark.asyncio
async def test_history_trim_preserves_complete_turn_pairs() -> None:
    calls = []
    async def executor(request):
        calls.append(request)
        return _answer(len(calls))

    chat = EngineChat(session_id="bounded", engine_executor=executor)
    for i in range(60):
        await chat.send_message(f"question-{i}")
    assert len(chat._history) == 100
    assert chat._history[0] == {"role": "user", "content": "question-10"}
    assert chat._history[1] == {"role": "assistant", "content": "answer-11"}
    assert chat._history[-1] == {"role": "assistant", "content": "answer-60"}
    assert len(calls[-1].history) == 100


@pytest.mark.asyncio
async def test_utf8_byte_cap_evicts_whole_oldest_turns() -> None:
    count = 0
    async def executor(_request):
        nonlocal count
        count += 1
        return _answer(count, content="μ" * 24_000)

    chat = EngineChat(session_id="bytes", engine_executor=executor)
    for i in range(16):
        await chat.send_message(f"question-{i}")
    assert len(chat._history) < 32
    assert chat._history
    assert chat._history[0]["role"] == "user"
    assert chat._history[-1]["role"] == "assistant"
    assert sum(len(x["content"].encode("utf-8")) for x in chat._history) <= 512 * 1024
