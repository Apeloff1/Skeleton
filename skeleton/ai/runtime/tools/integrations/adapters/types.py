"""Provider-neutral request, response and stream-chunk types.

These immutable value objects are the single interface every provider adapter
speaks.  They deliberately avoid any vendor wire format; adapters translate
to and from their transport at the edge.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .errors import InvalidRequestError, ResponseFormatError

__all__ = [
    "Role",
    "FinishReason",
    "ChunkKind",
    "ProviderCapability",
    "Message",
    "ToolSpec",
    "ToolCall",
    "ToolResult",
    "Usage",
    "ChatRequest",
    "ChatResponse",
    "StreamChunk",
    "StreamAccumulator",
    "canonical_json",
    "arguments_digest",
]


def canonical_json(value: Any) -> str:
    """Deterministic JSON encoding used for digests and cache keys."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def arguments_digest(arguments: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(arguments)).encode("utf-8")).hexdigest()


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    @classmethod
    def parse(cls, value: "Role | str") -> "Role":
        if isinstance(value, Role):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise InvalidRequestError(f"unknown message role {value!r}") from exc


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    CANCELLED = "cancelled"
    ERROR = "error"

    @classmethod
    def parse(cls, value: "FinishReason | str | None") -> "FinishReason":
        if isinstance(value, FinishReason):
            return value
        if value is None:
            return cls.STOP
        normalized = str(value).strip().lower()
        aliases = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "eos": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
            "function_call": "tool_calls",
        }
        normalized = aliases.get(normalized, normalized)
        try:
            return cls(normalized)
        except ValueError:
            return cls.STOP


class ChunkKind(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    FINISH = "finish"


class ProviderCapability(str, Enum):
    CHAT = "chat"
    STREAMING = "streaming"
    TOOLS = "tools"
    JSON_MODE = "json_mode"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    OFFLINE = "offline"


@dataclass(frozen=True)
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise InvalidRequestError("tool call id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidRequestError("tool call name must be a non-empty string")
        if not isinstance(self.arguments, Mapping):
            raise InvalidRequestError("tool call arguments must be a mapping")
        object.__setattr__(self, "arguments", dict(self.arguments))

    @property
    def digest(self) -> str:
        return arguments_digest(self.arguments)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": dict(self.arguments)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolCall":
        arguments = payload.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                raise ResponseFormatError(f"tool call arguments are not valid JSON: {exc}") from exc
        if not isinstance(arguments, Mapping):
            raise ResponseFormatError("tool call arguments must decode to an object")
        return cls(id=str(payload.get("id", "")), name=str(payload.get("name", "")), arguments=arguments)


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", Role.parse(self.role))
        if not isinstance(self.content, str):
            raise InvalidRequestError("message content must be a string")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        if self.role is Role.TOOL and not self.tool_call_id:
            raise InvalidRequestError("tool messages must reference a tool_call_id")
        if self.tool_calls and self.role is not Role.ASSISTANT:
            raise InvalidRequestError("only assistant messages may carry tool calls")

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(Role.SYSTEM, content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(Role.USER, content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: Iterable[ToolCall] = ()) -> "Message":
        return cls(Role.ASSISTANT, content, tool_calls=tuple(tool_calls))

    @classmethod
    def tool(cls, tool_call_id: str, content: str, name: str | None = None) -> "Message":
        return cls(Role.TOOL, content, name=name, tool_call_id=tool_call_id)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = [call.as_dict() for call in self.tool_calls]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Message":
        calls = tuple(ToolCall.from_dict(item) for item in payload.get("tool_calls", ()) or ())
        content = payload.get("content")
        return cls(
            role=Role.parse(payload.get("role", "user")),
            content="" if content is None else str(content),
            name=payload.get("name"),
            tool_call_id=payload.get("tool_call_id"),
            tool_calls=calls,
        )


@dataclass(frozen=True)
class ToolSpec:
    """Declarative description of a tool offered to a model."""

    name: str
    description: str = ""
    parameters: Mapping[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidRequestError("tool name must be a non-empty string")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
        if any(ch not in allowed for ch in self.name) or len(self.name) > 128:
            raise InvalidRequestError(f"tool name {self.name!r} contains unsupported characters")
        if not isinstance(self.parameters, Mapping):
            raise InvalidRequestError("tool parameters must be a JSON-schema mapping")
        object.__setattr__(self, "parameters", dict(self.parameters))
        object.__setattr__(self, "capabilities", tuple(sorted(set(self.capabilities))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: Any = None
    is_error: bool = False
    error_code: str | None = None
    duration_ms: float = 0.0

    def as_text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return canonical_json(self.content)

    def as_message(self) -> Message:
        return Message.tool(self.call_id, self.as_text(), name=self.name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "content": self.content,
            "is_error": self.is_error,
            "error_code": self.error_code,
            "duration_ms": round(self.duration_ms, 3),
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __post_init__(self) -> None:
        for name in ("prompt_tokens", "completion_tokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ResponseFormatError(f"usage.{name} must be a non-negative integer")

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens, self.completion_tokens + other.completion_tokens)

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ChatRequest:
    messages: tuple[Message, ...]
    model: str | None = None
    tools: tuple[ToolSpec, ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()
    json_mode: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    required_capabilities: frozenset[ProviderCapability] = frozenset()

    def __post_init__(self) -> None:
        messages = tuple(
            item if isinstance(item, Message) else Message.from_dict(item) for item in self.messages
        )
        if not messages:
            raise InvalidRequestError("a chat request needs at least one message")
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "stop", tuple(self.stop))
        object.__setattr__(self, "metadata", dict(self.metadata))
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise InvalidRequestError("tool names must be unique within a request")
        if self.temperature is not None and not (0.0 <= float(self.temperature) <= 2.0):
            raise InvalidRequestError("temperature must be within [0, 2]")
        if self.max_tokens is not None and (not isinstance(self.max_tokens, int) or self.max_tokens <= 0):
            raise InvalidRequestError("max_tokens must be a positive integer")
        caps = set(ProviderCapability(c) for c in self.required_capabilities)
        caps.add(ProviderCapability.CHAT)
        if self.tools:
            caps.add(ProviderCapability.TOOLS)
        if self.json_mode:
            caps.add(ProviderCapability.JSON_MODE)
        object.__setattr__(self, "required_capabilities", frozenset(caps))

    @classmethod
    def from_prompt(cls, prompt: str, *, system: str | None = None, **kwargs: Any) -> "ChatRequest":
        messages: list[Message] = []
        if system:
            messages.append(Message.system(system))
        messages.append(Message.user(prompt))
        return cls(messages=tuple(messages), **kwargs)

    def with_messages(self, extra: Sequence[Message]) -> "ChatRequest":
        return replace(self, messages=self.messages + tuple(extra))

    def with_model(self, model: str | None) -> "ChatRequest":
        return replace(self, model=model)

    @property
    def last_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.role is Role.USER:
                return message.content
        return ""

    @property
    def system_text(self) -> str:
        return "\n".join(m.content for m in self.messages if m.role is Role.SYSTEM)

    def fingerprint(self) -> str:
        payload = {
            "messages": [m.as_dict() for m in self.messages],
            "model": self.model,
            "tools": [t.as_dict() for t in self.tools],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stop": list(self.stop),
            "json_mode": self.json_mode,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "messages": [m.as_dict() for m in self.messages],
            "model": self.model,
            "tools": [t.as_dict() for t in self.tools],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stop": list(self.stop),
            "json_mode": self.json_mode,
            "metadata": dict(self.metadata),
            "required_capabilities": sorted(c.value for c in self.required_capabilities),
        }


@dataclass(frozen=True)
class ChatResponse:
    text: str
    provider: str
    model: str
    finish_reason: FinishReason = FinishReason.STOP
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    attempts: int = 1
    fallback_used: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "finish_reason", FinishReason.parse(self.finish_reason))
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.tool_calls and self.finish_reason is FinishReason.STOP:
            object.__setattr__(self, "finish_reason", FinishReason.TOOL_CALLS)

    def as_message(self) -> Message:
        return Message.assistant(self.text, self.tool_calls)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason.value,
            "tool_calls": [c.as_dict() for c in self.tool_calls],
            "usage": self.usage.as_dict(),
            "latency_ms": round(self.latency_ms, 3),
            "attempts": self.attempts,
            "fallback_used": self.fallback_used,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StreamChunk:
    """One incremental unit of a streamed response."""

    kind: ChunkKind
    index: int
    text: str = ""
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    finish_reason: FinishReason | None = None
    provider: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ChunkKind(self.kind))
        if not isinstance(self.index, int) or self.index < 0:
            raise ResponseFormatError("stream chunk index must be a non-negative integer")
        if self.kind is ChunkKind.TEXT and not isinstance(self.text, str):
            raise ResponseFormatError("text chunk requires string text")
        if self.kind is ChunkKind.TOOL_CALL and self.tool_call is None:
            raise ResponseFormatError("tool_call chunk requires a tool_call")
        if self.kind is ChunkKind.USAGE and self.usage is None:
            raise ResponseFormatError("usage chunk requires usage")
        if self.kind is ChunkKind.FINISH:
            object.__setattr__(self, "finish_reason", FinishReason.parse(self.finish_reason))

    @classmethod
    def text_delta(cls, index: int, text: str, **kw: Any) -> "StreamChunk":
        return cls(ChunkKind.TEXT, index, text=text, **kw)

    @classmethod
    def finish(cls, index: int, reason: FinishReason | str = FinishReason.STOP, **kw: Any) -> "StreamChunk":
        return cls(ChunkKind.FINISH, index, finish_reason=FinishReason.parse(reason), **kw)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind.value, "index": self.index}
        if self.text:
            payload["text"] = self.text
        if self.tool_call is not None:
            payload["tool_call"] = self.tool_call.as_dict()
        if self.usage is not None:
            payload["usage"] = self.usage.as_dict()
        if self.finish_reason is not None:
            payload["finish_reason"] = self.finish_reason.value
        if self.provider:
            payload["provider"] = self.provider
        if self.model:
            payload["model"] = self.model
        return payload


class StreamAccumulator:
    """Fold a chunk stream into a :class:`ChatResponse`, validating ordering."""

    def __init__(self, provider: str = "", model: str = "") -> None:
        self.provider = provider
        self.model = model
        self._parts: list[str] = []
        self._tool_calls: list[ToolCall] = []
        self._usage = Usage()
        self._finish: FinishReason | None = None
        self._next_index = 0

    @property
    def finished(self) -> bool:
        return self._finish is not None

    @property
    def text(self) -> str:
        return "".join(self._parts)

    @property
    def chunk_count(self) -> int:
        return self._next_index

    def add(self, chunk: StreamChunk) -> None:
        if self._finish is not None:
            raise ResponseFormatError("stream produced a chunk after its finish chunk")
        if chunk.index != self._next_index:
            raise ResponseFormatError(
                f"stream chunk out of order: expected index {self._next_index}, got {chunk.index}"
            )
        self._next_index += 1
        if chunk.provider and not self.provider:
            self.provider = chunk.provider
        if chunk.model and not self.model:
            self.model = chunk.model
        if chunk.kind is ChunkKind.TEXT:
            self._parts.append(chunk.text)
        elif chunk.kind is ChunkKind.TOOL_CALL and chunk.tool_call is not None:
            self._tool_calls.append(chunk.tool_call)
        elif chunk.kind is ChunkKind.USAGE and chunk.usage is not None:
            self._usage = self._usage + chunk.usage
        elif chunk.kind is ChunkKind.FINISH:
            self._finish = chunk.finish_reason or FinishReason.STOP

    def build(self, *, latency_ms: float = 0.0, attempts: int = 1, fallback_used: bool = False) -> ChatResponse:
        return ChatResponse(
            text=self.text,
            provider=self.provider,
            model=self.model,
            finish_reason=self._finish or FinishReason.STOP,
            tool_calls=tuple(self._tool_calls),
            usage=self._usage,
            latency_ms=latency_ms,
            attempts=attempts,
            fallback_used=fallback_used,
        )
