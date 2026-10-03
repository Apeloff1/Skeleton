"""The single provider interface every model adapter implements.

A provider exposes two coroutines: :meth:`Provider.complete` for a whole
response and :meth:`Provider.stream` for an async iterator of
:class:`StreamChunk`.  Concrete adapters usually implement one and inherit
the other from :class:`BaseProvider`, which derives streaming from completion
(single text chunk + finish) or completion from streaming (accumulate).
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping

from .deadline import CancellationToken, Deadline
from .errors import InvalidRequestError
from .types import (
    ChatRequest,
    ChatResponse,
    ChunkKind,
    ProviderCapability,
    StreamAccumulator,
    StreamChunk,
    Usage,
)

__all__ = ["ProviderInfo", "CallContext", "Provider", "BaseProvider", "HealthStatus"]


@dataclass(frozen=True)
class ProviderInfo:
    """Static description of a provider used by the registry for routing."""

    name: str
    capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.CHAT})
    models: tuple[str, ...] = ()
    default_model: str = ""
    priority: int = 100
    local: bool = False
    cost_per_1k_tokens: float = 0.0
    tags: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidRequestError("provider name must be a non-empty string")
        object.__setattr__(self, "capabilities", frozenset(ProviderCapability(c) for c in self.capabilities))
        object.__setattr__(self, "models", tuple(self.models))
        object.__setattr__(self, "tags", frozenset(self.tags))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if not self.default_model and self.models:
            object.__setattr__(self, "default_model", self.models[0])
        if self.cost_per_1k_tokens < 0:
            raise InvalidRequestError("cost_per_1k_tokens must be non-negative")

    def supports(self, required: frozenset[ProviderCapability] | set[ProviderCapability]) -> bool:
        return set(required).issubset(self.capabilities)

    def serves_model(self, model: str | None) -> bool:
        if not model:
            return True
        if not self.models:
            return True
        return model in self.models

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": sorted(c.value for c in self.capabilities),
            "models": list(self.models),
            "default_model": self.default_model,
            "priority": self.priority,
            "local": self.local,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "tags": sorted(self.tags),
        }


@dataclass
class CallContext:
    """Per-call controls threaded through every adapter."""

    deadline: Deadline = field(default_factory=Deadline.never)
    token: CancellationToken = field(default_factory=CancellationToken)
    attempt: int = 1
    trace_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def check(self, what: str = "provider call") -> None:
        self.token.check()
        self.deadline.check(what)


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str = ""
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"healthy": self.healthy, "detail": self.detail, "latency_ms": round(self.latency_ms, 3)}


class Provider(abc.ABC):
    """Abstract provider.  Implementations must be safe to call concurrently."""

    @property
    @abc.abstractmethod
    def info(self) -> ProviderInfo: ...

    @property
    def name(self) -> str:
        return self.info.name

    @abc.abstractmethod
    async def complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse: ...

    @abc.abstractmethod
    def stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]: ...

    async def health(self) -> HealthStatus:
        return HealthStatus(True, "no health probe implemented")

    async def aclose(self) -> None:
        return None


class BaseProvider(Provider):
    """Convenience base: implement ``_complete`` and/or ``_stream``.

    If only ``_complete`` is overridden, streaming yields one text chunk, any
    tool-call chunks, a usage chunk and a finish chunk.  If only ``_stream``
    is overridden, completion accumulates the stream.
    """

    def __init__(self, info: ProviderInfo) -> None:
        self._info = info

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def resolve_model(self, request: ChatRequest) -> str:
        return request.model or self._info.default_model or self._info.name

    async def _complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        raise NotImplementedError

    def _stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError

    def _overrides(self, method: str) -> bool:
        return getattr(type(self), method) is not getattr(BaseProvider, method)

    async def complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        ctx.check()
        started = time.perf_counter()
        if self._overrides("_complete"):
            return await self._complete(request, ctx)
        if not self._overrides("_stream"):
            raise NotImplementedError(f"{type(self).__name__} implements neither _complete nor _stream")
        acc = StreamAccumulator(self.name, self.resolve_model(request))
        async for chunk in self._stream(request, ctx):
            ctx.token.check()
            acc.add(chunk)
        return acc.build(latency_ms=(time.perf_counter() - started) * 1000.0, attempts=ctx.attempt)

    async def stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]:
        ctx.check()
        if self._overrides("_stream"):
            async for chunk in self._stream(request, ctx):
                ctx.token.check()
                yield chunk
            return
        response = await self.complete(request, ctx)
        index = 0
        if response.text:
            yield StreamChunk.text_delta(index, response.text, provider=response.provider, model=response.model)
            index += 1
        for call in response.tool_calls:
            yield StreamChunk(ChunkKind.TOOL_CALL, index, tool_call=call, provider=response.provider)
            index += 1
        if response.usage != Usage():
            yield StreamChunk(ChunkKind.USAGE, index, usage=response.usage, provider=response.provider)
            index += 1
        yield StreamChunk.finish(index, response.finish_reason, provider=response.provider, model=response.model)
