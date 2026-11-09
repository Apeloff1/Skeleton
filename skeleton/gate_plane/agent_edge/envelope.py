"""Inter-agent message envelope.

Every message exchanged between agents travels in an :class:`Envelope`. The
envelope carries identity (``message_id``), causality (``correlation_id`` for
the whole exchange, ``causation_id`` for the direct parent), ordering scope
(``conversation_id`` + per-conversation ``sequence``), delivery controls
(``priority``, ``ttl_s``, ``max_attempts``) and an opaque JSON payload.

Envelopes are immutable; delivery bookkeeping (attempts, leases) lives in the
bus. Wire form is canonical JSON so a digest is stable across processes and
can back idempotency keys.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

ENVELOPE_SCHEMA = "agent-envelope/v1"
MIN_PRIORITY = 0  # control traffic, most urgent
MAX_PRIORITY = 9  # bulk, least urgent
DEFAULT_PRIORITY = 4
DEFAULT_TTL_S = 300.0
MAX_TTL_S = 86_400.0
DEFAULT_MAX_ATTEMPTS = 5
MAX_ATTEMPTS_CAP = 50
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_HEADERS = 32

_AGENT_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,62}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")
_TOPIC_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,95}$")
_HEADER_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class EnvelopeError(ValueError):
    """Raised when an envelope violates the schema."""


def validate_agent_id(value: str) -> str:
    if not isinstance(value, str) or not _AGENT_RE.match(value):
        raise EnvelopeError(f"invalid agent id {value!r}")
    return value


def validate_message_id(value: str, *, field_name: str = "id") -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise EnvelopeError(f"invalid {field_name} {value!r}")
    return value


def validate_topic(value: str) -> str:
    if not isinstance(value, str) or not _TOPIC_RE.match(value):
        raise EnvelopeError(f"invalid topic {value!r}")
    return value


def new_id(prefix: str = "msg") -> str:
    return f"{prefix}-{secrets.token_hex(12)}"


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


@dataclass(frozen=True)
class Envelope:
    """Immutable inter-agent message."""

    message_id: str
    sender: str
    recipient: str
    topic: str
    payload: Mapping[str, Any]
    conversation_id: str
    correlation_id: str
    causation_id: Optional[str] = None
    sequence: int = 0
    priority: int = DEFAULT_PRIORITY
    created_at: float = 0.0
    ttl_s: float = DEFAULT_TTL_S
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    idempotency_key: Optional[str] = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_message_id(self.message_id, field_name="message_id")
        validate_agent_id(self.sender)
        validate_agent_id(self.recipient)
        validate_topic(self.topic)
        validate_message_id(self.conversation_id, field_name="conversation_id")
        validate_message_id(self.correlation_id, field_name="correlation_id")
        if self.causation_id is not None:
            validate_message_id(self.causation_id, field_name="causation_id")
            if self.causation_id == self.message_id:
                raise EnvelopeError("a message cannot cause itself")
        if self.idempotency_key is not None:
            validate_message_id(self.idempotency_key, field_name="idempotency_key")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise EnvelopeError("sequence must be a non-negative int")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise EnvelopeError("priority must be an int")
        if not MIN_PRIORITY <= self.priority <= MAX_PRIORITY:
            raise EnvelopeError(f"priority must be within {MIN_PRIORITY}..{MAX_PRIORITY}")
        if not 0 < float(self.ttl_s) <= MAX_TTL_S:
            raise EnvelopeError(f"ttl_s must be within (0, {MAX_TTL_S}]")
        if isinstance(self.max_attempts, bool) or not 1 <= int(self.max_attempts) <= MAX_ATTEMPTS_CAP:
            raise EnvelopeError(f"max_attempts must be within 1..{MAX_ATTEMPTS_CAP}")
        if not isinstance(self.payload, Mapping):
            raise EnvelopeError("payload must be a JSON object")
        try:
            size = len(canonical(dict(self.payload)))
        except (TypeError, ValueError) as exc:
            raise EnvelopeError(f"payload is not JSON serialisable: {exc}") from exc
        if size > MAX_PAYLOAD_BYTES:
            raise EnvelopeError(f"payload too large: {size} > {MAX_PAYLOAD_BYTES}")
        if len(self.headers) > MAX_HEADERS:
            raise EnvelopeError(f"too many headers (>{MAX_HEADERS})")
        for k, v in self.headers.items():
            if not isinstance(k, str) or not _HEADER_RE.match(k) or not isinstance(v, str) or len(v) > 512:
                raise EnvelopeError(f"invalid header {k!r}")

    # -- derived -----------------------------------------------------------------
    @property
    def expires_at(self) -> float:
        return self.created_at + float(self.ttl_s)

    def expired(self, now: float) -> bool:
        return now >= self.expires_at

    @property
    def dedup_key(self) -> str:
        """Key used by the bus for duplicate suppression.

        An explicit ``idempotency_key`` is scoped by sender so two agents
        cannot collide; otherwise the message id is the identity.
        """
        if self.idempotency_key:
            return f"idem:{self.sender}:{self.idempotency_key}"
        return f"id:{self.message_id}"

    def digest(self) -> str:
        return hashlib.sha256(canonical(self.to_wire())).hexdigest()

    # -- construction ------------------------------------------------------------
    @classmethod
    def new(
        cls,
        *,
        sender: str,
        recipient: str,
        topic: str,
        payload: Optional[Mapping[str, Any]] = None,
        conversation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        priority: int = DEFAULT_PRIORITY,
        ttl_s: float = DEFAULT_TTL_S,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        idempotency_key: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        now: float = 0.0,
        message_id: Optional[str] = None,
    ) -> "Envelope":
        mid = message_id or new_id("msg")
        conv = conversation_id or new_id("conv")
        return cls(
            message_id=mid,
            sender=sender,
            recipient=recipient,
            topic=topic,
            payload=dict(payload or {}),
            conversation_id=conv,
            correlation_id=correlation_id or conv,
            causation_id=causation_id,
            priority=priority,
            created_at=float(now),
            ttl_s=float(ttl_s),
            max_attempts=int(max_attempts),
            idempotency_key=idempotency_key,
            headers=dict(headers or {}),
        )

    def reply(
        self,
        *,
        topic: Optional[str] = None,
        payload: Optional[Mapping[str, Any]] = None,
        now: float = 0.0,
        priority: Optional[int] = None,
        ttl_s: Optional[float] = None,
        message_id: Optional[str] = None,
    ) -> "Envelope":
        """Build a reply: same conversation and correlation, caused by this message."""
        return Envelope.new(
            sender=self.recipient,
            recipient=self.sender,
            topic=topic or f"{self.topic}.reply"[:96],
            payload=payload,
            conversation_id=self.conversation_id,
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            priority=self.priority if priority is None else priority,
            ttl_s=self.ttl_s if ttl_s is None else ttl_s,
            max_attempts=self.max_attempts,
            now=now,
            message_id=message_id,
        )

    def forward(self, recipient: str, *, now: float = 0.0, message_id: Optional[str] = None) -> "Envelope":
        """Re-address to another agent (e.g. routing fallback); causation points at the original."""
        return Envelope.new(
            sender=self.recipient,
            recipient=recipient,
            topic=self.topic,
            payload=self.payload,
            conversation_id=self.conversation_id,
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            priority=self.priority,
            ttl_s=max(1.0, self.expires_at - now) if now else self.ttl_s,
            max_attempts=self.max_attempts,
            headers=self.headers,
            now=now,
            message_id=message_id,
        )

    def with_sequence(self, sequence: int) -> "Envelope":
        return replace(self, sequence=int(sequence))

    # -- wire --------------------------------------------------------------------
    def to_wire(self) -> Dict[str, Any]:
        wire: Dict[str, Any] = {
            "schema": ENVELOPE_SCHEMA,
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "topic": self.topic,
            "payload": dict(self.payload),
            "conversation_id": self.conversation_id,
            "correlation_id": self.correlation_id,
            "sequence": self.sequence,
            "priority": self.priority,
            "created_at": self.created_at,
            "ttl_s": self.ttl_s,
            "max_attempts": self.max_attempts,
        }
        if self.causation_id is not None:
            wire["causation_id"] = self.causation_id
        if self.idempotency_key is not None:
            wire["idempotency_key"] = self.idempotency_key
        if self.headers:
            wire["headers"] = dict(sorted(self.headers.items()))
        return wire

    @classmethod
    def from_wire(cls, data: Mapping[str, Any]) -> "Envelope":
        if not isinstance(data, Mapping):
            raise EnvelopeError("envelope must be an object")
        schema = data.get("schema", ENVELOPE_SCHEMA)
        if schema != ENVELOPE_SCHEMA:
            raise EnvelopeError(f"unsupported schema {schema!r}")
        try:
            return cls(
                message_id=data["message_id"],
                sender=data["sender"],
                recipient=data["recipient"],
                topic=data["topic"],
                payload=dict(data.get("payload") or {}),
                conversation_id=data["conversation_id"],
                correlation_id=data.get("correlation_id") or data["conversation_id"],
                causation_id=data.get("causation_id"),
                sequence=int(data.get("sequence", 0)),
                priority=int(data.get("priority", DEFAULT_PRIORITY)),
                created_at=float(data.get("created_at", 0.0)),
                ttl_s=float(data.get("ttl_s", DEFAULT_TTL_S)),
                max_attempts=int(data.get("max_attempts", DEFAULT_MAX_ATTEMPTS)),
                idempotency_key=data.get("idempotency_key"),
                headers=dict(data.get("headers") or {}),
            )
        except KeyError as exc:
            raise EnvelopeError(f"missing field {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            if isinstance(exc, EnvelopeError):
                raise
            raise EnvelopeError(str(exc)) from exc


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_PRIORITY",
    "DEFAULT_TTL_S",
    "ENVELOPE_SCHEMA",
    "Envelope",
    "EnvelopeError",
    "MAX_ATTEMPTS_CAP",
    "MAX_PAYLOAD_BYTES",
    "MAX_PRIORITY",
    "MAX_TTL_S",
    "MIN_PRIORITY",
    "canonical",
    "new_id",
    "validate_agent_id",
    "validate_message_id",
    "validate_topic",
]
