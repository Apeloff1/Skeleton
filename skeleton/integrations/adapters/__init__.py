"""Provider-neutral model adapters with canonical tool authority.

The provider runtime remains independent of vendor transports and supports
deterministic offline fallback. Tool execution is additive and has exactly one
authority source: the frozen :mod:`skeleton.kernel.capsec` gate. Callers pass
a signed capability token; verified token identity becomes the tool context
identity, and denied actions fail closed before side effects.
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
