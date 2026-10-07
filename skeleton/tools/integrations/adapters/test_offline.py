"""Tests for the deterministic offline provider."""

from __future__ import annotations

import asyncio
import json
import socket

import pytest

from .offline import (
    OfflineProvider,
    OfflineSkill,
    estimate_tokens,
    extractive_summary,
    safe_arithmetic,
)
from .provider import CallContext
from .types import ChatRequest, ChunkKind, FinishReason, Message, ProviderCapability, ToolSpec


def run(coro):
    return asyncio.run(coro)


def ask(provider: OfflineProvider, request: ChatRequest):
    return run(provider.complete(request, CallContext()))


def test_info_marks_local_offline_capabilities():
    info = OfflineProvider().info
    assert info.local
    assert ProviderCapability.OFFLINE in info.capabilities
    assert ProviderCapability.STREAMING in info.capabilities


def test_never_touches_the_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("offline provider opened a network connection")

    async def main():
        # Patch after the event loop exists (the loop itself uses a socketpair).
        monkeypatch.setattr(socket, "create_connection", refuse)
        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "getaddrinfo", refuse)
        return await OfflineProvider().complete(ChatRequest.from_prompt("hello"), CallContext())

    resp = run(main())
    assert "offline" in resp.text


@pytest.mark.parametrize(
    "expr,value",
    [("1+2*3", 7), ("(2+3)**2", 25), ("-4 + 10 / 4", -1.5), ("7 // 2", 3), ("7 % 4", 3)],
)
def test_safe_arithmetic(expr, value):
    assert safe_arithmetic(expr) == value


@pytest.mark.parametrize("expr", ["__import__('os')", "2**1000", "a+1", "True + 1", "[1][0]", "1" * 300])
def test_safe_arithmetic_rejects_unsafe(expr):
    with pytest.raises((ValueError, SyntaxError)):
        safe_arithmetic(expr)


def test_arithmetic_skill():
    p = OfflineProvider()
    assert ask(p, ChatRequest.from_prompt("What is 6 * 7?")).text == "6 * 7 = 42"
    assert ask(p, ChatRequest.from_prompt("10 / 4")).text == "10 / 4 = 2.5"
    assert ask(p, ChatRequest.from_prompt("compute 8/2")).metadata["skill"] == "arithmetic"
    assert ask(p, ChatRequest.from_prompt("what is 1/0")).metadata["skill"] != "arithmetic"


def test_greeting_and_status_skills():
    p = OfflineProvider()
    assert ask(p, ChatRequest.from_prompt("hey!")).metadata["skill"] == "greeting"
    assert ask(p, ChatRequest.from_prompt("which model are you?")).metadata["skill"] == "status"


def test_summarize_skill_inline_and_from_history():
    p = OfflineProvider()
    text = (
        "Skeleton routes requests to providers. Providers can fail. The offline provider keeps Skeleton "
        "useful when providers fail. Weather today is mild. Skeleton providers expose one interface."
    )
    inline = ask(p, ChatRequest.from_prompt(f"summarize: {text}"))
    assert inline.metadata["skill"] == "summarize"
    assert inline.text.count(".") <= 3
    history = ChatRequest(
        messages=(Message.user(text), Message.assistant("ok"), Message.user("tl;dr")),
    )
    assert ask(p, history).metadata["skill"] == "summarize"
    empty = ask(p, ChatRequest.from_prompt("summarize"))
    assert "nothing to summarize" in empty.text


def test_extractive_summary_keeps_order_and_short_text():
    assert extractive_summary("One. Two.") == "One. Two."
    long = "Cats purr. Dogs bark loudly at dogs. Birds sing. Dogs chase cats and dogs. Fish swim."
    summary = extractive_summary(long, max_sentences=2)
    parts = summary.split(". ")
    assert len(parts) == 2
    assert long.index(parts[0][:8]) < long.index(parts[1][:8])
    assert extractive_summary("the the the. a a a. of of.", max_sentences=1) == "the the the."


def test_fallback_answer_is_deterministic_and_honest():
    p = OfflineProvider()
    req = ChatRequest.from_prompt("Explain quantum chromodynamics in depth.")
    a, b = ask(p, req), ask(p, req)
    assert a.text == b.text
    assert "offline" in a.text
    assert a.metadata["skill"] == "fallback"
    assert a.usage.completion_tokens == estimate_tokens(a.text)


def test_json_mode_returns_valid_json():
    resp = ask(OfflineProvider(), ChatRequest.from_prompt("what is 2+2", json_mode=True))
    payload = json.loads(resp.text)
    assert payload == {"answer": "2+2 = 4", "source": "offline", "skill": "arithmetic"}


def test_max_tokens_truncates_with_length_finish():
    resp = ask(OfflineProvider(), ChatRequest.from_prompt("Tell me a long story please", max_tokens=3))
    assert len(resp.text.split()) == 3
    assert resp.finish_reason is FinishReason.LENGTH


def test_stop_sequences_cut_output():
    resp = ask(OfflineProvider(), ChatRequest.from_prompt("what is 3+4", stop=("=",)))
    assert resp.text == "3+4 "


def test_tool_routing_from_explicit_invocation():
    tools = (ToolSpec("clock", parameters={"type": "object", "properties": {"tz": {"type": "string"}}}),)
    p = OfflineProvider()
    resp = ask(p, ChatRequest.from_prompt('call clock {"tz": "UTC"}', tools=tools))
    assert resp.finish_reason is FinishReason.TOOL_CALLS
    assert resp.tool_calls[0].name == "clock" and resp.tool_calls[0].arguments == {"tz": "UTC"}
    slash = ask(p, ChatRequest.from_prompt("/clock", tools=tools))
    assert slash.tool_calls[0].arguments == {}
    unknown = ask(p, ChatRequest.from_prompt("/weather", tools=tools))
    assert not unknown.tool_calls
    broken = ask(p, ChatRequest.from_prompt("call clock {oops", tools=tools))
    assert not broken.tool_calls


def test_tool_result_is_echoed_not_reinvoked():
    tools = (ToolSpec("clock"),)
    req = ChatRequest(
        messages=(Message.user("/clock"), Message.tool("c1", "12:00", name="clock")),
        tools=tools,
    )
    resp = ask(OfflineProvider(), req)
    assert not resp.tool_calls
    assert resp.text == "Tool clock returned: 12:00"


def test_custom_skills_and_broken_skill_isolated():
    def broken(_r):
        raise RuntimeError("bug")

    p = OfflineProvider(skills=[OfflineSkill("broken", broken), OfflineSkill("pong", lambda r: "pong")])
    resp = ask(p, ChatRequest.from_prompt("ping"))
    assert resp.text == "pong" and resp.metadata["skill"] == "pong"


def test_generator_used_and_failures_degrade():
    good = OfflineProvider(generator=lambda prompt: "local model says hi")
    assert ask(good, ChatRequest.from_prompt("anything")).metadata["skill"] == "generator"

    def bad(_p):
        raise RuntimeError("model crashed")

    degraded = OfflineProvider(generator=bad)
    assert ask(degraded, ChatRequest.from_prompt("hello")).metadata["skill"] == "greeting"
    blank = OfflineProvider(generator=lambda prompt: "   ")
    assert ask(blank, ChatRequest.from_prompt("hello")).metadata["skill"] == "greeting"


def test_streaming_word_chunks_reassemble():
    p = OfflineProvider(chunk_words=2)
    req = ChatRequest.from_prompt("which provider is this")

    async def collect():
        return [c async for c in p.stream(req, CallContext())]

    chunks = run(collect())
    text = "".join(c.text for c in chunks if c.kind is ChunkKind.TEXT)
    assert text == ask(p, req).text
    assert chunks[-1].kind is ChunkKind.FINISH
    assert chunks[-2].kind is ChunkKind.USAGE
    assert [c.index for c in chunks] == list(range(len(chunks)))
    with pytest.raises(ValueError):
        OfflineProvider(chunk_words=0)


def test_health_always_ok():
    assert run(OfflineProvider().health()).healthy
