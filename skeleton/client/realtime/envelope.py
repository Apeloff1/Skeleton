"""Envelope v1 dataclasses for SDK users (re-export of ``skeleton.realtime.envelope``).

One schema, one implementation: the server hub and the SDK share the same
dataclass so field names (snake_case) and validation can never drift.
"""

from skeleton.realtime.envelope import (  # noqa: F401
    CHANNELS,
    CONTROL_TYPES,
    KNOWN_EVENT_TYPES,
    SCHEMA_VERSION,
    STREAM_LAGGED,
    STREAM_REAUTH,
    STREAM_RESET,
    ControlEvent,
    EnvelopeError,
    RealtimeEvent,
    parse_cursor,
)

__all__ = [
    "CHANNELS",
    "CONTROL_TYPES",
    "ControlEvent",
    "EnvelopeError",
    "KNOWN_EVENT_TYPES",
    "RealtimeEvent",
    "SCHEMA_VERSION",
    "STREAM_LAGGED",
    "STREAM_REAUTH",
    "STREAM_RESET",
    "parse_cursor",
]
