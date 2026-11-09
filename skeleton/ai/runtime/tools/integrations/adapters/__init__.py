"""Provider-neutral model adapter runtime.

This package is the current-main salvage of the provider/runtime portion of
the former integration-adapter draft.  It intentionally excludes tool
execution and capability authority: tool/provider side effects must bind to
the canonical :mod:`skeleton.kernel.capsec` gate in a separate integration
slice.

The surface here is safe to use for provider selection, retry/circuit/deadline
handling, deterministic offline fallback, and provider-neutral chat types.
"""

from .capsec import KernelToolAuthorizer, ToolAuthorization, declared_capability_action, tool_actions
from .circuit import BreakerBoard, CircuitBreaker, CircuitBreakerConfig, CircuitState
from .client import ClientConfig, ModelClient
from .deadline import CancellationToken, Deadline, ManualClock, MonotonicClock
from .errors import (
    AuthenticationError,
    CircuitOpenError,
    ConfigurationError,
    DeadlineExceededError,
    IntegrationError,
    InvalidRequestError,
    NoProviderAvailableError,
    OperationCancelledError,
    ProviderError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    RateLimitedError,
    RetryExhaustedError,
)
from .observe import AdapterEvent, EventLog, MetricsRecorder, ObserverHub
from .offline import OfflineProvider
from .provider import BaseProvider, CallContext, HealthStatus, Provider, ProviderInfo
from .registry import ProviderRegistry, SelectionPolicy
from .retry import NO_RETRY, Jitter, RetryPolicy
from .tool_loop import LoopResult, ToolLoop, ToolLoopConfig
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
    "AuthenticationError",
    "BaseProvider",
    "BreakerBoard",
    "CallContext",
    "CancellationToken",
    "ChatRequest",
    "ChatResponse",
    "ChunkKind",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitOpenError",
    "CircuitState",
    "ClientConfig",
    "ConfigurationError",
    "Deadline",
    "DeadlineExceededError",
    "EventLog",
    "FinishReason",
    "HealthStatus",
    "IntegrationError",
    "KernelToolAuthorizer",
    "InvalidRequestError",
    "Jitter",
    "ManualClock",
    "LoopResult",
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
    "ProviderNotFoundError",
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
    "ToolLoop",
    "ToolLoopConfig",
    "ToolAuthorization",
    "ToolContext",
    "ToolExecutor",
    "ToolExecutorConfig",
    "ToolRegistry",
    "ToolCall",
    "FunctionTool",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "declared_capability_action",
    "tool",
    "tool_actions",
]
