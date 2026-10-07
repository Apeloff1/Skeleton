"""Tests for the provider interface, BaseProvider derivations and registry."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from .errors import DuplicateRegistrationError, InvalidRequestError, NoProviderAvailableError, ProviderNotFoundError
from .fakes import ScriptedProvider
from .offline import OfflineProvider
from .provider import BaseProvider, CallContext, ProviderInfo
from .registry import ProviderRegistry, SelectionPolicy
from .types import ChatRequest, ChatResponse, ChunkKind, ProviderCapability, StreamChunk, ToolCall, ToolSpec, Usage


def run(coro):
    return asyncio.run(coro)


def test_provider_info_normalises_and_validates():
    info = ProviderInfo("p", capabilities=frozenset({"chat", "tools"}), models=("m1", "m2"))
    assert info.default_model == "m1"
    assert info.supports({ProviderCapability.CHAT, ProviderCapability.TOOLS})
    assert not info.supports({ProviderCapability.VISION})
    assert info.serves_model("m2") and not info.serves_model("zz") and info.serves_model(None)
    assert ProviderInfo("open").serves_model("anything")
    with pytest.raises(InvalidRequestError):
        ProviderInfo("")
    with pytest.raises(InvalidRequestError):
        ProviderInfo("p", cost_per_1k_tokens=-1)
    assert info.as_dict()["capabilities"] == ["chat", "tools"]


class CompleteOnly(BaseProvider):
    def __init__(self) -> None:
        super().__init__(ProviderInfo("complete-only"))

    async def _complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        return ChatResponse(
            text="hello",
            provider=self.name,
            model="m",
            tool_calls=(ToolCall("1", "t"),),
            usage=Usage(2, 1),
        )


class StreamOnly(BaseProvider):
    def __init__(self) -> None:
        super().__init__(ProviderInfo("stream-only", models=("s1",)))

    async def _stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]:
        yield StreamChunk.text_delta(0, "ab")
        yield StreamChunk.text_delta(1, "cd")
        yield StreamChunk.finish(2)


class Neither(BaseProvider):
    def __init__(self) -> None:
        super().__init__(ProviderInfo("neither"))


async def collect(provider, request):
    return [c async for c in provider.stream(request, CallContext())]


def test_stream_derived_from_complete():
    chunks = run(collect(CompleteOnly(), ChatRequest.from_prompt("x")))
    assert [c.kind for c in chunks] == [ChunkKind.TEXT, ChunkKind.TOOL_CALL, ChunkKind.USAGE, ChunkKind.FINISH]
    assert [c.index for c in chunks] == [0, 1, 2, 3]


def test_complete_derived_from_stream():
    resp = run(StreamOnly().complete(ChatRequest.from_prompt("x"), CallContext()))
    assert resp.text == "abcd" and resp.model == "s1" and resp.provider == "stream-only"


def test_provider_with_no_implementation_raises():
    with pytest.raises(NotImplementedError):
        run(Neither().complete(ChatRequest.from_prompt("x"), CallContext()))


def test_complete_checks_cancellation_first():
    ctx = CallContext()
    ctx.token.cancel()
    with pytest.raises(Exception) as info:
        run(CompleteOnly().complete(ChatRequest.from_prompt("x"), ctx))
    assert info.value.code == "cancelled"  # type: ignore[attr-defined]


def test_registry_register_get_and_duplicates():
    reg = ProviderRegistry()
    p = reg.register(ScriptedProvider("a", ["x"]))
    assert reg.get("a") is p and "a" in reg and len(reg) == 1 and list(reg) == ["a"]
    with pytest.raises(DuplicateRegistrationError):
        reg.register(ScriptedProvider("a", ["y"]))
    reg.register(ScriptedProvider("a", ["y"]), replace=True)
    with pytest.raises(ProviderNotFoundError):
        reg.get("missing")
    with pytest.raises(ProviderNotFoundError):
        reg.info("missing")
    reg.unregister("a")
    with pytest.raises(ProviderNotFoundError):
        reg.unregister("a")


def test_lazy_factory_built_once_and_name_checked():
    reg = ProviderRegistry()
    built: list[int] = []

    def factory():
        built.append(1)
        return ScriptedProvider("lazy", ["x"])

    reg.register_factory(ProviderInfo("lazy"), factory)
    assert reg.snapshot()["instantiated"] == []
    assert reg.get("lazy") is reg.get("lazy")
    assert built == [1]
    reg.register_factory(ProviderInfo("liar"), lambda: ScriptedProvider("other", ["x"]))
    with pytest.raises(DuplicateRegistrationError):
        reg.get("liar")


def test_candidates_order_by_priority_and_capabilities():
    reg = ProviderRegistry()
    reg.register(ScriptedProvider("slow", ["x"], priority=50))
    reg.register(ScriptedProvider("fast", ["x"], priority=5))
    reg.register(
        ScriptedProvider("chat-only", ["x"], priority=1, capabilities=frozenset({ProviderCapability.CHAT}))
    )
    reg.register(OfflineProvider(), fallback=True)
    plain = [i.name for i in reg.candidates(ChatRequest.from_prompt("x"))]
    assert plain == ["chat-only", "fast", "slow", "offline"]
    tools = ChatRequest.from_prompt("x", tools=(ToolSpec("t"),))
    assert [i.name for i in reg.candidates(tools)] == ["fast", "slow", "offline"]
    assert [i.name for i in reg.candidates(tools, include_fallback=False)] == ["fast", "slow"]
    assert [i.name for i in reg.candidates(tools, exclude=["fast"])] == ["slow", "offline"]


def test_selection_policy_local_cheap_allow_deny():
    reg = ProviderRegistry()
    reg.register(ScriptedProvider("cloud-cheap", ["x"], priority=20, cost=0.1))
    reg.register(ScriptedProvider("cloud-pricey", ["x"], priority=10, cost=5.0))
    reg.register(ScriptedProvider("laptop", ["x"], priority=90, local=True))
    reg.register(OfflineProvider(), fallback=True)
    req = ChatRequest.from_prompt("x")
    names = lambda pol: [i.name for i in reg.candidates(req, policy=pol)]  # noqa: E731
    assert names(SelectionPolicy(prefer_local=True))[0] == "laptop"
    assert names(SelectionPolicy(local_only=True)) == ["laptop", "offline"]
    assert names(SelectionPolicy(prefer_cheapest=True))[:2] == ["laptop", "cloud-cheap"]
    assert names(SelectionPolicy(deny=frozenset({"cloud-pricey", "laptop"}))) == ["cloud-cheap", "offline"]
    assert names(SelectionPolicy(allow=frozenset({"laptop"}))) == ["laptop", "offline"]


def test_model_filtering_and_disable():
    reg = ProviderRegistry()
    reg.register(ScriptedProvider("a", ["x"], models=("m-a",)))
    reg.register(ScriptedProvider("b", ["x"], models=("m-b",), priority=20))
    req = ChatRequest.from_prompt("x", model="m-b")
    assert [i.name for i in reg.candidates(req)] == ["b"]
    reg.disable("b")
    assert reg.candidates(req) == []
    with pytest.raises(NoProviderAvailableError):
        reg.select(req)
    reg.enable("b")
    assert reg.select(req).name == "b"
    with pytest.raises(ProviderNotFoundError):
        reg.disable("zzz")


def test_fallback_management():
    reg = ProviderRegistry()
    reg.register(OfflineProvider())
    reg.set_fallback("offline")
    assert reg.fallback_name == "offline"
    with pytest.raises(ProviderNotFoundError):
        reg.set_fallback("nope")
    reg.unregister("offline")
    assert reg.fallback_name is None


def test_registry_aclose_closes_instances():
    reg = ProviderRegistry()
    p = reg.register(ScriptedProvider("a", ["x"]))
    run(reg.aclose())
    assert p.closed
