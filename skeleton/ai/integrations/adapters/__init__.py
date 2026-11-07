"""Skeleton integration adapters: one interface for model providers and tools.

``skeleton.integrations.adapters`` is a new, additive surface.  The legacy
``skeleton.integrations`` package keeps re-exporting
``skeleton.tools.integrations`` unchanged; nothing here modifies it.

Quick start (fully offline)::

    from skeleton.integrations.adapters import build_default_stack

    stack = build_default_stack()           # offline fallback, deny-all capsec
    text = await stack.client.ask("what is 6 * 7?")

Module map:

* ``types`` / ``errors`` — request/response/stream-chunk values, error taxonomy
* ``provider`` / ``registry`` — the provider interface and capability routing
* ``retry`` / ``circuit`` / ``deadline`` — backoff+jitter, breakers, deadlines,
  cancellation
* ``client`` — :class:`ModelClient`, retries + breaker + fallback walk
* ``offline`` — deterministic local provider (no network)
* ``capsec`` / ``tools`` / ``tool_loop`` — fail-closed capability gate, tool
  adapters and the model↔tool loop
* ``sse`` / ``http`` / ``openai_compat`` — transport and an OpenAI-compatible
  adapter (works with local servers such as llama.cpp / Ollama / vLLM)
* ``config`` — declarative stack construction
"""

from __future__ import annotations

from .capsec import (
    B031_INTEGRATION_NOTE,
    AllowAllChecker,
    AllowListChecker,
    CapabilityChecker,
    CapabilityDecision,
    CapabilityRequest,
    CapsecGate,
    CheckerChain,
    DenyAllChecker,
    load_checker,
)
from .circuit import BreakerBoard, CircuitBreaker, CircuitBreakerConfig, CircuitState
from .client import ClientConfig, ModelClient
from .deadline import CancellationToken, Deadline, ManualClock, MonotonicClock
from .errors import (
    AuthenticationError,
    CapabilityDeniedError,
    CircuitOpenError,
    ConfigurationError,
    DeadlineExceededError,
    IntegrationError,
    InvalidRequestError,
    NoProviderAvailableError,
    OperationCancelledError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    RetryExhaustedError,
    ToolError,
)
from .observe import AdapterEvent, EventLog, MetricsRecorder, ObserverHub
from .offline import OfflineProvider
from .provider import BaseProvider, CallContext, HealthStatus, Provider, ProviderInfo
from .registry import ProviderRegistry, SelectionPolicy
from .retry import NO_RETRY, Jitter, RetryPolicy
from .tools import FunctionTool, ToolAdapter, ToolContext, ToolExecutor, ToolExecutorConfig, ToolRegistry, tool
from .types import (
    ChatRequest,
    ChatResponse,
    ChunkKind,
    FinishReason,
    Message,
    ProviderCapability,
    Role,
    StreamAccumulator,
    StreamChunk,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)

__all__ = [
    "AdapterEvent",
    "AllowAllChecker",
    "AllowListChecker",
    "AuthenticationError",
    "B031_INTEGRATION_NOTE",
    "BaseProvider",
    "BreakerBoard",
    "CallContext",
    "CancellationToken",
    "CapabilityChecker",
    "CapabilityDecision",
    "CapabilityDeniedError",
    "CapabilityRequest",
    "CapsecGate",
    "ChatRequest",
    "ChatResponse",
    "CheckerChain",
    "ChunkKind",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitOpenError",
    "CircuitState",
    "ClientConfig",
    "ConfigurationError",
    "Deadline",
    "DeadlineExceededError",
    "DenyAllChecker",
    "EventLog",
    "FinishReason",
    "FunctionTool",
    "HealthStatus",
    "IntegrationError",
    "InvalidRequestError",
    "Jitter",
    "ManualClock",
    "Message",
    "MetricsRecorder",
    "ModelClient",
    "MonotonicClock",
    "NO_RETRY",
    "NoProviderAvailableError",
    "ObserverHub",
    "OfflineProvider",
    "OperationCancelledError",
    "Provider",
    "ProviderCapability",
    "ProviderError",
    "ProviderInfo",
    "ProviderRegistry",
    "ProviderUnavailableError",
    "RateLimitedError",
    "RetryExhaustedError",
    "RetryPolicy",
    "Role",
    "SelectionPolicy",
    "StreamAccumulator",
    "StreamChunk",
    "ToolAdapter",
    "ToolCall",
    "ToolContext",
    "ToolError",
    "ToolExecutor",
    "ToolExecutorConfig",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "load_checker",
    "tool",
]
