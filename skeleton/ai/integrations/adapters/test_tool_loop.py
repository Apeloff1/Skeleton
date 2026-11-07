"""Tests for the model ↔ tool loop."""

from __future__ import annotations

import asyncio
import random

import pytest

from .capsec import AllowAllChecker, AllowListChecker, CapsecGate
from .client import ClientConfig, ModelClient
from .deadline import CancellationToken, ManualClock
from .errors import OperationCancelledError
from .fakes import ScriptedProvider
from .offline import OfflineProvider
from .registry import ProviderRegistry
from .tool_loop import ToolLoop, ToolLoopConfig
from .tools import ToolExecutor, ToolRegistry, tool
from .types import ChatRequest, ChatResponse, Role, ToolCall, Usage


@tool("clock", capabilities=["time.read"])
def clock(tz: str = "UTC") -> str:
    return f"12:00 {tz}"


def make_client(*providers) -> ModelClient:
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p)
    reg.register(OfflineProvider(), fallback=True)
    return ModelClient(reg, ClientConfig(), clock=ManualClock(), rng=random.Random(0))


def call_response(*calls: ToolCall) -> ChatResponse:
    return ChatResponse(text="", provider="m", model="m", tool_calls=calls, usage=Usage(1, 1))


def run(coro):
    return asyncio.run(coro)


def test_config_validation():
    with pytest.raises(ValueError):
        ToolLoopConfig(max_rounds=0)
    with pytest.raises(ValueError):
        ToolLoopConfig(max_repeats=0)


def test_principal_required():
    with pytest.raises(ValueError):
        ToolLoop(make_client(), ToolExecutor(ToolRegistry()), principal="")


def test_offline_end_to_end_tool_round():
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowAllChecker()))
    loop = ToolLoop(make_client(), executor, principal="agent:a")
    result = run(loop.run(ChatRequest.from_prompt('call clock {"tz": "CET"}')))
    assert result.stop_reason == "answered"
    assert result.rounds == 2
    assert result.tool_results[0].content == "12:00 CET"
    assert result.text == "Tool clock returned: 12:00 CET"
    assert [m.role for m in result.messages] == [Role.USER, Role.ASSISTANT, Role.TOOL, Role.ASSISTANT]


def test_registered_tools_offered_automatically():
    model = ScriptedProvider("m", ["no tools needed"])
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowAllChecker()))
    run(ToolLoop(make_client(model), executor, principal="p").run(ChatRequest.from_prompt("hi")))
    assert [t.name for t in model.calls[0].tools] == ["clock"]
    model2 = ScriptedProvider("m", ["x"])
    cfg = ToolLoopConfig(offer_registered_tools=False)
    run(ToolLoop(make_client(model2), executor, principal="p", config=cfg).run(ChatRequest.from_prompt("hi")))
    assert model2.calls[0].tools == ()


def test_denied_calls_are_fed_back_and_loop_continues():
    model = ScriptedProvider("m", [call_response(ToolCall("c1", "clock")), "ok, I could not read the time"])
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowListChecker({"*": ["tool.invoke:clock"]})))
    result = run(ToolLoop(make_client(model), executor, principal="p").run(ChatRequest.from_prompt("time?")))
    assert result.tool_results[0].error_code == "capability_denied"
    assert result.text == "ok, I could not read the time"
    second_request = model.calls[1]
    assert second_request.messages[-1].role is Role.TOOL
    assert "capability_denied" in second_request.messages[-1].content
    assert result.usage.total_tokens == 4


def test_repeated_call_detection():
    stuck = call_response(ToolCall("c", "clock", {"tz": "UTC"}))
    model = ScriptedProvider("m", [stuck])
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowAllChecker()))
    cfg = ToolLoopConfig(max_rounds=10, max_repeats=2)
    result = run(ToolLoop(make_client(model), executor, principal="p", config=cfg).run(ChatRequest.from_prompt("x")))
    assert result.stop_reason == "repeated_call"
    assert result.rounds == 3


def test_max_rounds_stop():
    responses = [call_response(ToolCall(f"c{i}", "clock", {"tz": f"T{i}"})) for i in range(5)]
    model = ScriptedProvider("m", responses)
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowAllChecker()))
    cfg = ToolLoopConfig(max_rounds=2, parallel=False)
    result = run(ToolLoop(make_client(model), executor, principal="p", config=cfg).run(ChatRequest.from_prompt("x")))
    assert result.stop_reason == "max_rounds" and result.rounds == 2
    assert len(result.tool_results) == 2
    assert result.as_dict()["stop_reason"] == "max_rounds"


def test_cancellation_stops_loop():
    token = CancellationToken()
    token.cancel()
    executor = ToolExecutor(ToolRegistry([clock]), CapsecGate(AllowAllChecker()))
    with pytest.raises(OperationCancelledError):
        run(ToolLoop(make_client(), executor, principal="p").run(ChatRequest.from_prompt("x"), token=token))
