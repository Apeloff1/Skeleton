"""Skeleton SDK realtime client (ADR-realtime-transport, PR #4101).

SSE subscriber with Last-Event-ID resume, full-jitter reconnect over the SDK
``RetryPolicy``, 45 s dead-stream detection and presence helpers. The v1
envelope dataclass is shared with the server (``skeleton.realtime``).

Not yet re-exported from ``skeleton.client``; that follows #4095.
"""

from .backoff import HEALTHY_RESET_SECONDS, REALTIME_RETRY_POLICY, ReconnectBackoff
from .client import DEAD_STREAM_SECONDS, RealtimeClient
from .envelope import CHANNELS, ControlEvent, EnvelopeError, RealtimeEvent
from .errors import (
    RealtimeAuthError,
    RealtimeConnectError,
    RealtimeError,
    RealtimeGaveUp,
    RealtimeHeartbeatTimeout,
    RealtimeProtocolError,
)
from .presence import HttpPresencePoster, PresenceClient
from .transport import HEARTBEAT, InProcessTransport, SSETransport

__all__ = [
    "CHANNELS",
    "ControlEvent",
    "DEAD_STREAM_SECONDS",
    "EnvelopeError",
    "HEALTHY_RESET_SECONDS",
    "HEARTBEAT",
    "HttpPresencePoster",
    "InProcessTransport",
    "PresenceClient",
    "REALTIME_RETRY_POLICY",
    "RealtimeAuthError",
    "RealtimeClient",
    "RealtimeConnectError",
    "RealtimeError",
    "RealtimeEvent",
    "RealtimeGaveUp",
    "RealtimeHeartbeatTimeout",
    "RealtimeProtocolError",
    "ReconnectBackoff",
    "SSETransport",
]
