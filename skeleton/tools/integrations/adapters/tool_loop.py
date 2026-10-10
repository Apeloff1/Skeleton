"""Model ↔ tool loop over :class:`ModelClient` and :class:`ToolExecutor`.

Each round asks the model; if it returns tool calls, every call is executed
through the canonical-capability executor using the run's signed token, and the results are appended as tool
messages before the next round.  The loop stops when the model answers
without tool calls, when ``max_rounds`` is reached, or when the same call
(name + argument digest) repeats ``max_repeats`` times, which catches models
stuck re-issuing a denied or failing call.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from .client import ModelClient
from .deadline import CancellationToken, Deadline
from .tools import ToolExecutor
from .types import ChatRequest, ChatResponse, Message, ToolResult, Usage

__all__ = ["ToolLoop", "ToolLoopConfig", "LoopResult"]


@dataclass(frozen=True)
class ToolLoopConfig:
    max_rounds: int = 8
    max_repeats: int = 3
    parallel: bool = True
    offer_registered_tools: bool = True

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if self.max_repeats < 1:
            raise ValueError("max_repeats must be >= 1")


@dataclass
class LoopResult:
    response: ChatResponse
    messages: list[Message]
    tool_results: list[ToolResult] = field(default_factory=list)
    rounds: int = 0
    stop_reason: str = "answered"
    usage: Usage = field(default_factory=Usage)

    @property
    def text(self) -> str:
        return self.response.text

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "rounds": self.rounds,
            "stop_reason": self.stop_reason,
            "usage": self.usage.as_dict(),
            "tool_results": [r.as_dict() for r in self.tool_results],
            "provider": self.response.provider,
        }


class ToolLoop:
    def __init__(
        self,
        client: ModelClient,
        executor: ToolExecutor,
        *,
        config: ToolLoopConfig | None = None,
    ) -> None:
        self.client = client
        self.executor = executor
        self.config = config or ToolLoopConfig()

    async def run(
        self,
        request: ChatRequest,
        *,
        cap: str | None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        **client_kwargs: Any,
    ) -> LoopResult:
        tok = token or CancellationToken()
        current = request
        if self.config.offer_registered_tools and not request.tools and len(self.executor.registry):
            current = replace(request, tools=self.executor.registry.specs())
        messages = list(current.messages)
        results: list[ToolResult] = []
        seen: Counter[tuple[str, str]] = Counter()
        usage = Usage()
        response: ChatResponse | None = None
        for round_no in range(1, self.config.max_rounds + 1):
            tok.check()
            response = await self.client.complete(current, deadline=deadline, token=tok, **client_kwargs)
            usage = usage + response.usage
            if not response.tool_calls:
                return LoopResult(response, messages + [response.as_message()], results, round_no, "answered", usage)
            messages.append(response.as_message())
            for call in response.tool_calls:
                seen[(call.name, call.digest)] += 1
            if any(count > self.config.max_repeats for count in seen.values()):
                return LoopResult(response, messages, results, round_no, "repeated_call", usage)
            if self.config.parallel:
                batch = await self.executor.execute_many(
                    response.tool_calls, cap=cap, deadline=deadline, token=tok
                )
            else:
                batch = [
                    await self.executor.execute(call, cap=cap, deadline=deadline, token=tok)
                    for call in response.tool_calls
                ]
            results.extend(batch)
            tool_messages = [r.as_message() for r in batch]
            messages.extend(tool_messages)
            current = current.with_messages([response.as_message(), *tool_messages])
        assert response is not None
        return LoopResult(response, messages, results, self.config.max_rounds, "max_rounds", usage)
