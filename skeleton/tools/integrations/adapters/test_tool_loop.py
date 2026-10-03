"""Tests for the signed-capability model ↔ tool loop."""

from __future__ import annotations

import asyncio
import random

import pytest

from skeleton.kernel.capabilities import TokenIssuer
from skeleton.kernel.capsec import Action, mint_scoped

from .capsec import tool_actions
from .client import ClientConfig, ModelClient
from .deadline import CancellationToken, ManualClock
from .errors import OperationCancelledError
from .fakes import ScriptedProvider
from .offline import OfflineProvider
from .registry import ProviderRegistry
from .tool_loop import ToolLoop, ToolLoopConfig
from .tools import ToolExecutor, ToolRegistry, tool
from .types import ChatRequest, ChatResponse, Role, ToolCall, Usage


@tool("clock", capabilities=("time.read",))
def clock(tz: str = "UTC") -> str:
    return f"12:00 {tz}"


def make_client(*providers) -> ModelClient:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    registry.register(OfflineProvider(), fallback=True)
    return ModelClient(
        registry,
        ClientConfig(),
        clock=ManualClock(),
        rng=random.Random(0),
    )


def make_executor(*adapters):
    issuer = TokenIssuer(secret=b"l" * 32)
    return issuer, ToolExecutor(ToolRegistry(adapters), issuer.gate())


def full_cap(issuer: TokenIssuer, name: str, capabilities=()):
    return mint_scoped(
        issuer,
        "agent:loop",
        tool_actions(name, capabilities),
        ttl_seconds=60,
    )


def call_response(*calls: ToolCall) -> ChatResponse:
    return ChatResponse(
        text="",
        provider="m",
        model="m",
        tool_calls=calls,
        usage=Usage(1, 1),
    )


def run(coro):
    return asyncio.run(coro)


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        ToolLoopConfig(max_rounds=0)
    with pytest.raises(ValueError):
        ToolLoopConfig(max_repeats=0)


def test_offline_end_to_end_tool_round_uses_signed_capability() -> None:
    issuer, executor = make_executor(clock)
    cap = full_cap(issuer, "clock", ("time.read",))
    loop = ToolLoop(make_client(), executor)

    result = run(
        loop.run(
            ChatRequest.from_prompt('call clock {"tz": "CET"}'),
            cap=cap,
        )
    )

    assert result.stop_reason == "answered"
    assert result.rounds == 2
    assert result.tool_results[0].content == "12:00 CET"
    assert result.text == "Tool clock returned: 12:00 CET"
    assert [m.role for m in result.messages] == [
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]


def test_registered_tools_are_offered_without_implying_authority() -> None:
    model = ScriptedProvider("m", ["no tools needed"])
    _issuer, executor = make_executor(clock)

    run(ToolLoop(make_client(model), executor).run(ChatRequest.from_prompt("hi"), cap=None))
    assert [tool_spec.name for tool_spec in model.calls[0].tools] == ["clock"]

    model2 = ScriptedProvider("m", ["x"])
    cfg = ToolLoopConfig(offer_registered_tools=False)
    run(
        ToolLoop(make_client(model2), executor, config=cfg).run(
            ChatRequest.from_prompt("hi"),
            cap=None,
        )
    )
    assert model2.calls[0].tools == ()


def test_under_scoped_call_is_fed_back_and_loop_continues() -> None:
    model = ScriptedProvider(
        "m",
        [
            call_response(ToolCall("c1", "clock")),
            "ok, I could not read the time",
        ],
    )
    issuer, executor = make_executor(clock)
    cap = mint_scoped(
        issuer,
        "agent:loop",
        (Action(scope="tool.clock", verb="invoke", resource="clock"),),
        ttl_seconds=60,
    )

    result = run(
        ToolLoop(make_client(model), executor).run(
            ChatRequest.from_prompt("time?"),
            cap=cap,
        )
    )

    assert result.tool_results[0].error_code == "capability_denied"
    assert result.text == "ok, I could not read the time"
    assert model.calls[1].messages[-1].role is Role.TOOL
    assert "capability_denied" in model.calls[1].messages[-1].content
    assert result.usage.total_tokens == 4


def test_repeated_call_detection_stops_loop() -> None:
    stuck = call_response(ToolCall("c", "clock", {"tz": "UTC"}))
    model = ScriptedProvider("m", [stuck])
    issuer, executor = make_executor(clock)
    cap = full_cap(issuer, "clock", ("time.read",))
    cfg = ToolLoopConfig(max_rounds=10, max_repeats=2)

    result = run(
        ToolLoop(make_client(model), executor, config=cfg).run(
            ChatRequest.from_prompt("x"),
            cap=cap,
        )
    )

    assert result.stop_reason == "repeated_call"
    assert result.rounds == 3


def test_max_rounds_stop_preserves_tool_results() -> None:
    responses = [
        call_response(ToolCall(f"c{i}", "clock", {"tz": f"T{i}"}))
        for i in range(5)
    ]
    model = ScriptedProvider("m", responses)
    issuer, executor = make_executor(clock)
    cap = full_cap(issuer, "clock", ("time.read",))
    cfg = ToolLoopConfig(max_rounds=2, parallel=False)

    result = run(
        ToolLoop(make_client(model), executor, config=cfg).run(
            ChatRequest.from_prompt("x"),
            cap=cap,
        )
    )

    assert result.stop_reason == "max_rounds"
    assert result.rounds == 2
    assert len(result.tool_results) == 2


def test_cancellation_stops_loop_before_model_or_tool_work() -> None:
    token = CancellationToken()
    token.cancel()
    _issuer, executor = make_executor(clock)

    with pytest.raises(OperationCancelledError):
        run(
            ToolLoop(make_client(), executor).run(
                ChatRequest.from_prompt("x"),
                cap=None,
                token=token,
            )
        )
