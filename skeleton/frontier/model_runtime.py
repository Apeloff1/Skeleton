"""Provider-neutral model execution contracts and adapters.

The frontier runtime keeps provider SDK objects behind adapters so orchestration
code can depend on stable request/response types while provider clients evolve.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol


class ModelCapability(str, Enum):
    CHAT = "chat"
    TOOLS = "tools"
    STREAMING = "streaming"
    EMBEDDINGS = "embeddings"
    STRUCTURED_OUTPUT = "structured_output"


class ProviderError(RuntimeError):
    """Base error raised at the provider/runtime boundary."""


class TransientProviderError(ProviderError):
    """Retryable provider failure."""


class ProviderTimeoutError(ProviderError):
    """Provider operation exceeded its runtime deadline."""


class ProviderCancelledError(ProviderError):
    """Provider operation was cancelled through a cancellation token."""


class UnsupportedCapabilityError(ProviderError):
    """Provider does not support a requested runtime capability."""


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model: str
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    response_schema: Mapping[str, Any] | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class ChatResponse:
    model: str
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    structured: Mapping[str, Any] | None = None
    usage: TokenUsage = TokenUsage()
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    model: str
    inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    model: str
    vectors: tuple[tuple[float, ...], ...]
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True, slots=True)
class StreamEvent:
    kind: str
    text_delta: str = ""
    tool_call_delta: Mapping[str, Any] | None = None
    response: ChatResponse | None = None


class CancellationToken:
    """Cooperative cancellation primitive shared across provider adapters."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ProviderCancelledError("model operation cancelled")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 2
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise TypeError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if isinstance(self.backoff_seconds, bool) or not isinstance(
            self.backoff_seconds, (int, float)
        ):
            raise TypeError("backoff_seconds must be a finite number")
        backoff = float(self.backoff_seconds)
        if not math.isfinite(backoff):
            raise ValueError("backoff_seconds must be finite")
        if backoff < 0:
            raise ValueError("backoff_seconds must not be negative")
        object.__setattr__(self, "backoff_seconds", backoff)


class ProviderAdapter(Protocol):
    name: str
    capabilities: frozenset[ModelCapability]

    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]: ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


class ModelRuntime:
    """Registry, capability negotiation, retry, timeout, and cancellation boundary."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, provider: ProviderAdapter) -> None:
        name = _normalized_text(provider.name, "provider name")
        if name in self._providers:
            raise ValueError(f"provider already registered: {name}")
        self._providers[name] = provider

    def resolve(self, provider_name: str) -> ProviderAdapter:
        name = _normalized_text(provider_name, "provider name")
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {name}") from exc

    def capabilities(self, provider_name: str) -> frozenset[ModelCapability]:
        return self.resolve(provider_name).capabilities

    def supports(self, provider_name: str, capability: ModelCapability) -> bool:
        return capability in self.capabilities(provider_name)

    async def chat(
        self,
        provider_name: str,
        request: ChatRequest,
        *,
        timeout_seconds: float | None = None,
        cancellation: CancellationToken | None = None,
        retry_policy: RetryPolicy = RetryPolicy(),
        allow_structured_fallback: bool = False,
    ) -> ChatResponse:
        provider = self.resolve(provider_name)
        required = {ModelCapability.CHAT}
        if request.tools:
            required.add(ModelCapability.TOOLS)
        if request.response_schema is not None:
            required.add(ModelCapability.STRUCTURED_OUTPUT)

        missing = required.difference(provider.capabilities)
        structured_fallback = False
        if missing == {ModelCapability.STRUCTURED_OUTPUT} and allow_structured_fallback:
            structured_fallback = True
            missing.clear()
        if missing:
            _raise_missing(provider, missing)

        actual_request = (
            replace(request, response_schema=None) if structured_fallback else request
        )
        response = await self._run_controlled(
            lambda: provider.chat(actual_request),
            timeout_seconds=timeout_seconds,
            cancellation=cancellation,
            retry_policy=retry_policy,
        )
        if structured_fallback:
            try:
                decoded = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    "structured-output fallback returned invalid JSON"
                ) from exc
            if not isinstance(decoded, Mapping):
                raise ProviderError(
                    "structured-output fallback must decode to a JSON object"
                )
            response = replace(response, structured=dict(decoded))
        return response

    async def embed(
        self,
        provider_name: str,
        request: EmbeddingRequest,
        *,
        timeout_seconds: float | None = None,
        cancellation: CancellationToken | None = None,
        retry_policy: RetryPolicy = RetryPolicy(),
    ) -> EmbeddingResponse:
        provider = self.resolve(provider_name)
        if ModelCapability.EMBEDDINGS not in provider.capabilities:
            _raise_missing(provider, {ModelCapability.EMBEDDINGS})
        return await self._run_controlled(
            lambda: provider.embed(request),
            timeout_seconds=timeout_seconds,
            cancellation=cancellation,
            retry_policy=retry_policy,
        )

    async def stream_chat(
        self,
        provider_name: str,
        request: ChatRequest,
        *,
        timeout_seconds: float | None = None,
        cancellation: CancellationToken | None = None,
        retry_policy: RetryPolicy = RetryPolicy(),
        allow_nonstream_fallback: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        provider = self.resolve(provider_name)
        required = {ModelCapability.CHAT}
        if request.tools:
            required.add(ModelCapability.TOOLS)
        missing = required.difference(provider.capabilities)
        if missing:
            _raise_missing(provider, missing)

        if ModelCapability.STREAMING not in provider.capabilities:
            if not allow_nonstream_fallback:
                _raise_missing(provider, {ModelCapability.STREAMING})
            response = await self.chat(
                provider_name,
                request,
                timeout_seconds=timeout_seconds,
                cancellation=cancellation,
                retry_policy=retry_policy,
            )
            if response.text:
                yield StreamEvent(kind="text_delta", text_delta=response.text)
            yield StreamEvent(kind="completed", response=response)
            return

        if request.response_schema is not None and (
            ModelCapability.STRUCTURED_OUTPUT not in provider.capabilities
        ):
            _raise_missing(provider, {ModelCapability.STRUCTURED_OUTPUT})
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cancellation is not None:
            cancellation.raise_if_cancelled()

        loop = asyncio.get_running_loop()
        deadline = None if timeout_seconds is None else loop.time() + timeout_seconds
        emitted_event = False
        for attempt in range(1, retry_policy.max_attempts + 1):
            iterator = provider.stream_chat(request).__aiter__()
            try:
                while True:
                    if cancellation is not None:
                        cancellation.raise_if_cancelled()
                    remaining = None if deadline is None else deadline - loop.time()
                    if remaining is not None and remaining <= 0:
                        raise ProviderTimeoutError("model stream exceeded its deadline")
                    try:
                        event = await _await_with_cancel(
                            iterator.__anext__(),
                            timeout_seconds=remaining,
                            cancellation=cancellation,
                        )
                    except StopAsyncIteration:
                        return
                    emitted_event = True
                    yield event
            except TransientProviderError:
                if emitted_event or attempt >= retry_policy.max_attempts:
                    raise
                await _controlled_sleep(
                    retry_policy.backoff_seconds,
                    deadline=deadline,
                    cancellation=cancellation,
                )

    async def _run_controlled(
        self,
        operation: Callable[[], Awaitable[Any]],
        *,
        timeout_seconds: float | None,
        cancellation: CancellationToken | None,
        retry_policy: RetryPolicy,
    ) -> Any:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cancellation is not None:
            cancellation.raise_if_cancelled()

        loop = asyncio.get_running_loop()
        deadline = None if timeout_seconds is None else loop.time() + timeout_seconds
        last_error: TransientProviderError | None = None
        for attempt in range(1, retry_policy.max_attempts + 1):
            remaining = None if deadline is None else deadline - loop.time()
            if remaining is not None and remaining <= 0:
                raise ProviderTimeoutError("model operation exceeded its deadline")
            try:
                return await _await_with_cancel(
                    operation(),
                    timeout_seconds=remaining,
                    cancellation=cancellation,
                )
            except TransientProviderError as exc:
                last_error = exc
                if attempt >= retry_policy.max_attempts:
                    raise
                await _controlled_sleep(
                    retry_policy.backoff_seconds,
                    deadline=deadline,
                    cancellation=cancellation,
                )

        assert last_error is not None
        raise last_error


async def _await_with_cancel(
    awaitable: Awaitable[Any],
    *,
    timeout_seconds: float | None,
    cancellation: CancellationToken | None,
) -> Any:
    operation = asyncio.ensure_future(awaitable)
    cancel_waiter: asyncio.Task[None] | None = None
    try:
        waiters: set[asyncio.Future[Any]] = {operation}
        if cancellation is not None:
            cancellation.raise_if_cancelled()
            cancel_waiter = asyncio.create_task(cancellation.wait())
            waiters.add(cancel_waiter)

        done, _ = await asyncio.wait(
            waiters,
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if operation in done:
            if cancel_waiter is not None:
                cancel_waiter.cancel()
            return await operation
        if cancel_waiter is not None and cancel_waiter in done:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            raise ProviderCancelledError("model operation cancelled")

        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        raise ProviderTimeoutError("model operation exceeded its deadline")
    finally:
        if cancel_waiter is not None and not cancel_waiter.done():
            cancel_waiter.cancel()


async def _controlled_sleep(
    seconds: float,
    *,
    deadline: float | None,
    cancellation: CancellationToken | None,
) -> None:
    if seconds <= 0:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        return
    loop = asyncio.get_running_loop()
    remaining = None if deadline is None else deadline - loop.time()
    if remaining is not None and remaining <= 0:
        raise ProviderTimeoutError("model operation exceeded its deadline")
    await _await_with_cancel(
        asyncio.sleep(seconds),
        timeout_seconds=remaining,
        cancellation=cancellation,
    )


def _normalized_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _raise_missing(
    provider: ProviderAdapter, capabilities: set[ModelCapability]
) -> None:
    names = ", ".join(sorted(capability.value for capability in capabilities))
    raise UnsupportedCapabilityError(
        f"provider {provider.name!r} lacks capabilities: {names}"
    )


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _message_payload(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.name is not None:
        payload["name"] = message.name
    return payload


def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.input_schema),
        },
    }


def _chat_kwargs(request: ChatRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": request.model,
        "messages": [_message_payload(message) for message in request.messages],
    }
    if request.tools:
        kwargs["tools"] = [_tool_payload(tool) for tool in request.tools]
    if request.response_schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_response",
                "schema": dict(request.response_schema),
                "strict": True,
            },
        }
    if request.max_output_tokens is not None:
        kwargs["max_completion_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        kwargs["temperature"] = request.temperature
    return kwargs


def _parse_tool_calls(raw_calls: Any) -> tuple[ToolCall, ...]:
    calls: list[ToolCall] = []
    for raw in raw_calls or ():
        function = _get(raw, "function", {})
        arguments = _get(function, "arguments", {})
        if isinstance(arguments, str):
            try:
                decoded = json.loads(arguments)
            except json.JSONDecodeError:
                decoded = {"_raw": arguments}
        elif isinstance(arguments, Mapping):
            decoded = dict(arguments)
        else:
            decoded = {"_raw": str(arguments)}
        calls.append(
            ToolCall(
                id=str(_get(raw, "id", "")),
                name=str(_get(function, "name", "")),
                arguments=decoded,
            )
        )
    return tuple(calls)


def _parse_usage(raw_usage: Any) -> TokenUsage:
    return TokenUsage(
        input_tokens=int(
            _get(raw_usage, "prompt_tokens", _get(raw_usage, "input_tokens", 0)) or 0
        ),
        output_tokens=int(
            _get(
                raw_usage,
                "completion_tokens",
                _get(raw_usage, "output_tokens", 0),
            )
            or 0
        ),
    )


def _parse_chat_response(raw: Any, requested_model: str) -> ChatResponse:
    choices = _get(raw, "choices", ()) or ()
    if not choices:
        raise ProviderError("provider returned no chat choices")
    choice = choices[0]
    message = _get(choice, "message", {})
    text = _get(message, "content", "") or ""
    if isinstance(text, Sequence) and not isinstance(text, (str, bytes)):
        text = "".join(str(_get(item, "text", "")) for item in text)
    text = str(text)
    return ChatResponse(
        model=str(_get(raw, "model", requested_model) or requested_model),
        text=text,
        tool_calls=_parse_tool_calls(_get(message, "tool_calls", ())),
        usage=_parse_usage(_get(raw, "usage", {})),
        finish_reason=(
            None
            if _get(choice, "finish_reason") is None
            else str(_get(choice, "finish_reason"))
        ),
    )


def _stream_event(raw: Any) -> StreamEvent | None:
    choices = _get(raw, "choices", ()) or ()
    if not choices:
        return None
    choice = choices[0]
    delta = _get(choice, "delta", {})
    text = _get(delta, "content", "") or ""
    if text:
        return StreamEvent(kind="text_delta", text_delta=str(text))
    raw_calls = _get(delta, "tool_calls", ()) or ()
    if raw_calls:
        call = raw_calls[0]
        function = _get(call, "function", {})
        return StreamEvent(
            kind="tool_call_delta",
            tool_call_delta={
                "index": _get(call, "index", 0),
                "id": _get(call, "id"),
                "name": _get(function, "name"),
                "arguments_json_delta": _get(function, "arguments", "") or "",
            },
        )
    return None


class OpenAIChatCompletionsAdapter:
    """Adapter for an injected OpenAI 2.x AsyncOpenAI-style client."""

    name = "openai"
    capabilities = frozenset(ModelCapability)

    def __init__(self, client: Any) -> None:
        self._client = client

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raw = await self._client.chat.completions.create(**_chat_kwargs(request))
        response = _parse_chat_response(raw, request.model)
        if request.response_schema is not None and response.text:
            try:
                decoded = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ProviderError("provider returned invalid structured JSON") from exc
            if isinstance(decoded, Mapping):
                response = replace(response, structured=dict(decoded))
        return response

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raw = await self._client.embeddings.create(
            model=request.model,
            input=list(request.inputs),
        )
        data = _get(raw, "data", ()) or ()
        vectors = tuple(
            tuple(float(value) for value in (_get(item, "embedding", ()) or ()))
            for item in data
        )
        return EmbeddingResponse(
            model=str(_get(raw, "model", request.model) or request.model),
            vectors=vectors,
            usage=_parse_usage(_get(raw, "usage", {})),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        stream = await self._client.chat.completions.create(
            **_chat_kwargs(request),
            stream=True,
        )
        text_parts: list[str] = []
        async for raw in stream:
            event = _stream_event(raw)
            if event is None:
                continue
            if event.kind == "text_delta":
                text_parts.append(event.text_delta)
            yield event
        yield StreamEvent(
            kind="completed",
            response=ChatResponse(model=request.model, text="".join(text_parts)),
        )


class LiteLLMAdapter:
    """Adapter for an injected litellm module/object with async entry points."""

    name = "litellm"
    capabilities = frozenset(ModelCapability)

    def __init__(self, client: Any) -> None:
        self._client = client

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raw = await self._client.acompletion(**_chat_kwargs(request))
        response = _parse_chat_response(raw, request.model)
        if request.response_schema is not None and response.text:
            try:
                decoded = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ProviderError("provider returned invalid structured JSON") from exc
            if isinstance(decoded, Mapping):
                response = replace(response, structured=dict(decoded))
        return response

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raw = await self._client.aembedding(
            model=request.model,
            input=list(request.inputs),
        )
        data = _get(raw, "data", ()) or ()
        vectors = tuple(
            tuple(float(value) for value in (_get(item, "embedding", ()) or ()))
            for item in data
        )
        return EmbeddingResponse(
            model=str(_get(raw, "model", request.model) or request.model),
            vectors=vectors,
            usage=_parse_usage(_get(raw, "usage", {})),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        stream = await self._client.acompletion(**_chat_kwargs(request), stream=True)
        text_parts: list[str] = []
        async for raw in stream:
            event = _stream_event(raw)
            if event is None:
                continue
            if event.kind == "text_delta":
                text_parts.append(event.text_delta)
            yield event
        yield StreamEvent(
            kind="completed",
            response=ChatResponse(model=request.model, text="".join(text_parts)),
        )
