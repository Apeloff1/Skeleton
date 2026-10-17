"""Realtime transport for the Skeleton app: live build progress, agent
activity and collaboration presence over Server-Sent Events.

Import surface for the API layer, the client SDK and job publishers. See
``docs/REALTIME_TRANSPORT.md`` and ADR
``docs/architecture/ADR-realtime-transport.md`` (PR #4101).
"""

from .envelope import (
    CHANNELS,
    CONTROL_TYPES,
    KNOWN_EVENT_TYPES,
    SCHEMA_VERSION,
    ControlEvent,
    EnvelopeError,
    RealtimeEvent,
    parse_cursor,
)
from .guard import PayloadSecretGuard, RealtimeSecretError
from .hub import PresenceMember, RealtimeAuthError, RealtimeHub, Subscription
from .sinks import HubJobEventSink, JobEventPublisher, NullJobEventPublisher, attach_hub
from .slo import SLO_TARGETS, RealtimeSLO

__all__ = [
    "CHANNELS",
    "CONTROL_TYPES",
    "ControlEvent",
    "EnvelopeError",
    "HubJobEventSink",
    "JobEventPublisher",
    "KNOWN_EVENT_TYPES",
    "NullJobEventPublisher",
    "PayloadSecretGuard",
    "PresenceMember",
    "RealtimeAuthError",
    "RealtimeEvent",
    "RealtimeHub",
    "RealtimeSLO",
    "RealtimeSecretError",
    "SCHEMA_VERSION",
    "SLO_TARGETS",
    "Subscription",
    "attach_hub",
    "parse_cursor",
]
