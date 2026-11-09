"""Canonical internal protocol envelope.

The envelope is transport-neutral and intentionally contains no socket, queue,
thread, or provider implementation. It binds internal messages to stable
operation, trace, deadline, idempotency, retry, and unknown-outcome semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping


PROTOCOL_ENVELOPE_VERSION = 1
MAX_PROTOCOL_PAYLOAD_FIELDS = 128
MAX_PROTOCOL_PAYLOAD_BYTES = 1_048_576
MAX_PROTOCOL_TRACKED_MESSAGES = 8192

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")


class ProtocolContractError(ValueError):
    """Raised when an internal protocol envelope violates the canonical contract."""


class RetryClass(str, Enum):
    NEVER = "never"
    IDEMPOTENT = "idempotent"
    RECONCILE_THEN_RETRY = "reconcile_then_retry"


class UnknownOutcomePolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    RECONCILE = "reconcile"
    IDEMPOTENT_REPLAY = "idempotent_replay"


def _bounded_id(name: str, value: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ProtocolContractError(f"invalid {name}")
    return value


def _deadline(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolContractError("deadline_utc must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProtocolContractError("deadline_utc is invalid RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ProtocolContractError("deadline_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    data = dict(payload)
    if len(data) > MAX_PROTOCOL_PAYLOAD_FIELDS:
        raise ProtocolContractError("protocol payload has too many fields")
    try:
        raw = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolContractError("protocol payload must be canonical JSON-shaped data") from exc
    if len(raw) > MAX_PROTOCOL_PAYLOAD_BYTES:
        raise ProtocolContractError("protocol payload exceeds byte bound")
    return MappingProxyType(data)


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    protocol: str
    message_id: str
    kind: str
    sender: str
    recipient: str
    operation_id: str
    correlation_id: str
    trace_id: str
    idempotency_key: str
    payload: Mapping[str, object] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_ENVELOPE_VERSION
    causation_id: str = ""
    span_id: str = ""
    deadline_utc: str | None = None
    attempt: int = 1
    retry_class: RetryClass = RetryClass.NEVER
    unknown_outcome_policy: UnknownOutcomePolicy = UnknownOutcomePolicy.FAIL_CLOSED

    def __post_init__(self) -> None:
        for name in (
            "protocol",
            "message_id",
            "kind",
            "sender",
            "recipient",
            "operation_id",
            "correlation_id",
            "trace_id",
            "idempotency_key",
        ):
            object.__setattr__(self, name, _bounded_id(name, getattr(self, name)))
        object.__setattr__(
            self,
            "causation_id",
            _bounded_id("causation_id", self.causation_id, optional=True),
        )
        object.__setattr__(
            self,
            "span_id",
            _bounded_id("span_id", self.span_id, optional=True),
        )
        if self.protocol_version != PROTOCOL_ENVELOPE_VERSION:
            raise ProtocolContractError("unsupported protocol envelope version")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt <= 0:
            raise ProtocolContractError("attempt must be a positive integer")
        if not isinstance(self.retry_class, RetryClass):
            object.__setattr__(self, "retry_class", RetryClass(self.retry_class))
        if not isinstance(self.unknown_outcome_policy, UnknownOutcomePolicy):
            object.__setattr__(
                self,
                "unknown_outcome_policy",
                UnknownOutcomePolicy(self.unknown_outcome_policy),
            )
        if (
            self.retry_class is RetryClass.NEVER
            and self.unknown_outcome_policy is UnknownOutcomePolicy.IDEMPOTENT_REPLAY
        ):
            raise ProtocolContractError(
                "idempotent replay outcome policy requires a retryable protocol class"
            )
        object.__setattr__(self, "deadline_utc", _deadline(self.deadline_utc))
        object.__setattr__(self, "payload", _canonical_payload(self.payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "kind": self.kind,
            "sender": self.sender,
            "recipient": self.recipient,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id or None,
            "trace_id": self.trace_id,
            "span_id": self.span_id or None,
            "deadline_utc": self.deadline_utc,
            "idempotency_key": self.idempotency_key,
            "attempt": self.attempt,
            "retry_class": self.retry_class.value,
            "unknown_outcome_policy": self.unknown_outcome_policy.value,
            "payload": dict(self.payload),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def trace_headers(self) -> dict[str, str]:
        return {
            "x-trace-id": self.trace_id,
            "x-span-id": self.span_id,
            "x-correlation-id": self.correlation_id,
            "x-causation-id": self.causation_id,
            "x-operation-id": self.operation_id,
        }

    def deadline_exceeded(self, *, now: datetime | None = None) -> bool:
        if self.deadline_utc is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ProtocolContractError("deadline check time must be timezone-aware")
        deadline = datetime.fromisoformat(self.deadline_utc[:-1] + "+00:00")
        return current.astimezone(timezone.utc) >= deadline


class ProtocolReplayGuard:
    """Bounded replay/idempotency guard for canonical protocol envelopes."""

    def __init__(self, *, max_messages: int = MAX_PROTOCOL_TRACKED_MESSAGES) -> None:
        if not isinstance(max_messages, int) or isinstance(max_messages, bool) or max_messages <= 0:
            raise ValueError("max_messages must be a positive integer")
        self.max_messages = max_messages
        self._digests: dict[str, str] = {}
        self._order: list[str] = []

    def accept(self, envelope: ProtocolEnvelope) -> bool:
        existing = self._digests.get(envelope.message_id)
        if existing is not None:
            if existing != envelope.digest:
                raise ProtocolContractError(
                    "message_id replay changed canonical envelope content"
                )
            return False
        if len(self._order) >= self.max_messages:
            oldest = self._order.pop(0)
            self._digests.pop(oldest, None)
        self._digests[envelope.message_id] = envelope.digest
        self._order.append(envelope.message_id)
        return True

    def seen(self, message_id: str) -> bool:
        return message_id in self._digests


__all__ = [
    "MAX_PROTOCOL_PAYLOAD_BYTES",
    "MAX_PROTOCOL_PAYLOAD_FIELDS",
    "MAX_PROTOCOL_TRACKED_MESSAGES",
    "PROTOCOL_ENVELOPE_VERSION",
    "ProtocolContractError",
    "ProtocolEnvelope",
    "ProtocolReplayGuard",
    "RetryClass",
    "UnknownOutcomePolicy",
]
