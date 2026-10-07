"""Scripted providers and tools for tests and local development.

``ScriptedProvider`` replays a list of outcomes, one per call: a string (text
reply), a :class:`ChatResponse`, an exception instance (raised), a
``("sleep", seconds)`` tuple (awaits real time before replying, to exercise
timeouts), or a ``("stream", [chunks...], error_after)`` tuple for streams
that may break mid-way.  When the script runs out, the last outcome repeats.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

from .provider import BaseProvider, CallContext, HealthStatus, ProviderInfo
from .types import ChatRequest, ChatResponse, ProviderCapability, StreamChunk, Usage

__all__ = ["ScriptedProvider", "ALL_CAPABILITIES"]

ALL_CAPABILITIES = frozenset(
    {
        ProviderCapability.CHAT,
        ProviderCapability.STREAMING,
        ProviderCapability.TOOLS,
        ProviderCapability.JSON_MODE,
    }
)


class ScriptedProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        script: Sequence[Any],
        *,
        capabilities: frozenset[ProviderCapability] = ALL_CAPABILITIES,
        priority: int = 10,
        local: bool = False,
        models: tuple[str, ...] = (),
        cost: float = 0.0,
        healthy: bool = True,
    ) -> None:
        super().__init__(
            ProviderInfo(
                name=name,
                capabilities=capabilities,
                priority=priority,
                local=local,
                models=models,
                cost_per_1k_tokens=cost,
            )
        )
        if not script:
            raise ValueError("script must contain at least one outcome")
        self._script = list(script)
        self.calls: list[ChatRequest] = []
        self.contexts: list[CallContext] = []
        self._healthy = healthy
        self.closed = False

    def _next(self) -> Any:
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]

    async def _resolve(self, outcome: Any, request: ChatRequest) -> ChatResponse:
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, tuple) and outcome and outcome[0] == "sleep":
            await asyncio.sleep(float(outcome[1]))
            reply = outcome[2] if len(outcome) > 2 else "slept"
            return await self._resolve(reply, request)
        if isinstance(outcome, ChatResponse):
            return outcome
        return ChatResponse(
            text=str(outcome),
            provider=self.name,
            model=self.resolve_model(request),
            usage=Usage(1, 1),
        )

    async def _complete(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        self.calls.append(request)
        self.contexts.append(ctx)
        outcome = self._next()
        if isinstance(outcome, tuple) and outcome and outcome[0] == "stream":
            text = "".join(c.text for c in outcome[1])
            return ChatResponse(text=text, provider=self.name, model=self.resolve_model(request))
        response = await self._resolve(outcome, request)
        return ChatResponse(
            text=response.text,
            provider=response.provider or self.name,
            model=response.model,
            finish_reason=response.finish_reason,
            tool_calls=response.tool_calls,
            usage=response.usage,
            attempts=ctx.attempt,
            metadata=response.metadata,
        )

    async def stream(self, request: ChatRequest, ctx: CallContext) -> AsyncIterator[StreamChunk]:
        peek = self._script[0]
        if isinstance(peek, tuple) and peek and peek[0] == "stream":
            self.calls.append(request)
            self.contexts.append(ctx)
            outcome = self._next()
            chunks: list[StreamChunk] = list(outcome[1])
            error_after = outcome[2] if len(outcome) > 2 else None
            for position, chunk in enumerate(chunks):
                if error_after is not None and position == error_after[0]:
                    raise error_after[1]
                await asyncio.sleep(0)
                yield chunk
            if error_after is not None and error_after[0] >= len(chunks):
                raise error_after[1]
            return
        async for chunk in super().stream(request, ctx):
            yield chunk

    async def health(self) -> HealthStatus:
        return HealthStatus(self._healthy, "scripted")

    async def aclose(self) -> None:
        self.closed = True
