"""Versioned realtime event envelope (schema v1).

Conforms to the TD ruling in ADR ``docs/architecture/ADR-realtime-transport.md``
(PR #4101). Transport-neutral and pure standard library, so the API layer,
the client SDK (``skeleton.client.realtime``) and job publishers can all
import it.

Wire shape (snake_case JSON)::

    {
      "v": 1,
      "id": "1792252800123000",          # monotonic per stream, string; == SSE id
      "ts": "2026-10-17T16:00:00.123Z",  # RFC 3339 UTC
      "channel": "build",                # build | agent | presence
      "type": "build.progress",
      "payload": {},                     # secret-scrubbed JSON object (<= 64 KB)
      "job_id": "job-7",                 # optional
      "correlation_id": "corr-1"         # optional
    }

Unknown fields are ignored on parse, so additive changes stay within v1;
breaking changes bump ``v``.

Control events ``stream.reset`` (cursor aged out: refetch over REST) and
``stream.lagged`` (``{"dropped": n}``, per-subscriber overflow) are sent as
SSE frames *without* an ``id:`` line so they never move the resume cursor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 64_000

CHANNEL_BUILD = "build"
CHANNEL_AGENT = "agent"
CHANNEL_PRESENCE = "presence"
CHANNELS: Tuple[str, ...] = (CHANNEL_BUILD, CHANNEL_AGENT, CHANNEL_PRESENCE)

KNOWN_EVENT_TYPES: Dict[str, Tuple[str, ...]] = {
    CHANNEL_BUILD: (
        "build.started",
        "build.progress",
        "build.log",
        "build.completed",
        "build.failed",
    ),
    CHANNEL_AGENT: ("agent.started", "agent.step", "agent.completed"),
    CHANNEL_PRESENCE: ("presence.joined", "presence.left", "presence.snapshot"),
}

STREAM_RESET = "stream.reset"
STREAM_LAGGED = "stream.lagged"
#: Max stream lifetime reached (Jenkins S2-4): reconnect now with a fresh
#: seal, from the same cursor, without backoff. Payload
#: ``{"reason": "max_lifetime", "lifetime_s": n, "cursor": "<id>-<epoch>"}``.
STREAM_REAUTH = "stream.reauth"
CONTROL_TYPES: Tuple[str, ...] = (STREAM_RESET, STREAM_LAGGED, STREAM_REAUTH)

ENVELOPE_FIELDS: Tuple[str, ...] = ("v", "id", "ts", "channel", "type", "payload", "job_id", "correlation_id")

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_ID_RE = re.compile(r"^[0-9]{1,19}$")
_EPOCH_RE = re.compile(r"^[0-9a-f]{1,16}$")


class EnvelopeError(ValueError):
    """An envelope or control event violates the v1 contract."""


def now_rfc3339() -> str:
    return format_ts(datetime.now(timezone.utc))


def format_ts(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def ts_from_ms(epoch_ms: float) -> str:
    return format_ts(datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc))


def parse_ts(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EnvelopeError("ts must be an RFC 3339 UTC string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EnvelopeError("ts must be an RFC 3339 UTC string") from exc
    if moment.tzinfo is None:
        raise EnvelopeError("ts must carry a UTC offset")
    return moment.astimezone(timezone.utc)


def ts_to_ms(value: str) -> float:
    return parse_ts(value).timestamp() * 1000.0


def validate_identifier(value: Optional[str], field_name: str) -> Optional[str]:
    """Bounded, printable identifiers only (no free text, no secrets)."""
    if value is None:
        return None
    if not isinstance(value, str) or not _IDENT_RE.match(value):
        raise EnvelopeError(f"{field_name} must match {_IDENT_RE.pattern}")
    return value


def validate_channel(channel: object) -> str:
    if channel not in CHANNELS:
        raise EnvelopeError(f"channel must be one of {CHANNELS}")
    return str(channel)


def validate_type(channel: str, event_type: object) -> str:
    if not isinstance(event_type, str) or not _TYPE_RE.match(event_type):
        raise EnvelopeError("type must be dotted lowercase, e.g. build.progress")
    if not event_type.startswith(channel + "."):
        raise EnvelopeError(f"type {event_type!r} does not belong to channel {channel!r}")
    return event_type


def channel_for_type(event_type: str) -> str:
    """Map ``build.progress`` -> ``build``; raises for unknown channels."""
    return validate_channel(str(event_type).split(".", 1)[0])


def parse_cursor(raw: Optional[str]) -> Optional[int]:
    """Parse a ``Last-Event-ID`` / ``?cursor=`` value. Empty -> None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not _ID_RE.match(text):
        raise EnvelopeError("cursor must be an event id (decimal string)")
    return int(text)


def parse_resume_cursor(raw: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Parse ``<id>`` (legacy) or ``<id>-<epoch>`` -> ``(seq, epoch)``.

    The hub writes ``id: <id>-<epoch>`` SSE lines (Jenkins S2-6) so a cursor
    issued by another process / an earlier hub instance is detected and gets
    ``stream.reset`` instead of a silently wrong replay.
    """
    if raw is None or not str(raw).strip():
        return None, None
    text = str(raw).strip()
    seq_text, sep, epoch = text.partition("-")
    if sep and not _EPOCH_RE.match(epoch):
        raise EnvelopeError("cursor epoch must be 1-16 lowercase hex characters")
    return parse_cursor(seq_text), (epoch if sep else None)


def _json_strict(body: Any, **kwargs: Any) -> str:
    """``json.dumps`` without ``default=str``: non-JSON-native values are refused."""
    try:
        return json.dumps(body, allow_nan=False, **kwargs)
    except (TypeError, ValueError) as exc:
        raise EnvelopeError(f"payload is not JSON-native: {exc}") from None


def _payload_size(payload: Mapping[str, Any]) -> int:
    return len(_json_strict(payload, separators=(",", ":")).encode("utf-8"))


def _dumps(body: Mapping[str, Any]) -> str:
    return _json_strict(body, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class RealtimeEvent:
    """One stored, replayable realtime event (the v1 envelope)."""

    id: str
    ts: str
    channel: str
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    job_id: Optional[str] = None
    correlation_id: Optional[str] = None
    v: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.v != SCHEMA_VERSION:
            raise EnvelopeError(f"unsupported schema version {self.v!r}")
        if not isinstance(self.id, str) or not _ID_RE.match(self.id) or int(self.id) < 1:
            raise EnvelopeError("id must be a positive decimal string")
        parse_ts(self.ts)
        validate_channel(self.channel)
        validate_type(self.channel, self.type)
        if not isinstance(self.payload, dict):
            raise EnvelopeError("payload must be a JSON object")
        if _payload_size(self.payload) > MAX_PAYLOAD_BYTES:
            raise EnvelopeError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
        validate_identifier(self.job_id, "job_id")
        validate_identifier(self.correlation_id, "correlation_id")

    @property
    def seq(self) -> int:
        """Integer form of ``id`` for ordering and cursor comparison."""
        return int(self.id)

    @property
    def known_type(self) -> bool:
        return self.type in KNOWN_EVENT_TYPES.get(self.channel, ())

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "v": self.v,
            "id": self.id,
            "ts": self.ts,
            "channel": self.channel,
            "type": self.type,
            "payload": self.payload,
        }
        if self.job_id is not None:
            body["job_id"] = self.job_id
        if self.correlation_id is not None:
            body["correlation_id"] = self.correlation_id
        return body

    def to_json(self) -> str:
        return _dumps(self.to_dict())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RealtimeEvent":
        """Parse a v1 envelope; unknown fields are ignored (ADR §3)."""
        if not isinstance(raw, Mapping):
            raise EnvelopeError("envelope must be an object")
        missing = [name for name in ("id", "ts", "channel", "type") if name not in raw]
        if missing:
            raise EnvelopeError(f"missing envelope fields {missing}")
        raw_id = raw["id"]
        if isinstance(raw_id, int) and not isinstance(raw_id, bool):
            raw_id = str(raw_id)
        payload = raw.get("payload")
        return cls(
            v=raw.get("v", SCHEMA_VERSION),
            id=raw_id,
            ts=raw["ts"],
            channel=raw["channel"],
            type=raw["type"],
            payload=dict(payload) if isinstance(payload, Mapping) else ({} if payload is None else payload),
            job_id=raw.get("job_id"),
            correlation_id=raw.get("correlation_id"),
        )

    @classmethod
    def from_json(cls, text: str) -> "RealtimeEvent":
        try:
            raw = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise EnvelopeError("envelope is not valid JSON") from exc
        return cls.from_dict(raw)


@dataclass(frozen=True)
class ControlEvent:
    """``stream.reset`` / ``stream.lagged``: never stored, never carries an id."""

    type: str
    ts: str
    payload: Dict[str, Any] = field(default_factory=dict)
    v: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.type not in CONTROL_TYPES:
            raise EnvelopeError(f"control type must be one of {CONTROL_TYPES}")
        if not isinstance(self.payload, dict):
            raise EnvelopeError("control payload must be an object")

    def to_dict(self) -> Dict[str, Any]:
        return {"v": self.v, "ts": self.ts, "type": self.type, "payload": self.payload}

    def to_json(self) -> str:
        return _dumps(self.to_dict())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ControlEvent":
        if not isinstance(raw, Mapping):
            raise EnvelopeError("control event must be an object")
        payload = raw.get("payload")
        return cls(
            v=raw.get("v", SCHEMA_VERSION),
            type=raw.get("type", ""),
            ts=str(raw.get("ts") or now_rfc3339()),
            payload=dict(payload) if isinstance(payload, Mapping) else {},
        )


__all__ = [
    "CHANNELS",
    "CHANNEL_AGENT",
    "CHANNEL_BUILD",
    "CHANNEL_PRESENCE",
    "CONTROL_TYPES",
    "ControlEvent",
    "ENVELOPE_FIELDS",
    "EnvelopeError",
    "KNOWN_EVENT_TYPES",
    "MAX_PAYLOAD_BYTES",
    "RealtimeEvent",
    "SCHEMA_VERSION",
    "STREAM_LAGGED",
    "STREAM_REAUTH",
    "STREAM_RESET",
    "channel_for_type",
    "format_ts",
    "now_rfc3339",
    "parse_cursor",
    "parse_resume_cursor",
    "parse_ts",
    "ts_from_ms",
    "ts_to_ms",
    "validate_channel",
    "validate_identifier",
    "validate_type",
]
